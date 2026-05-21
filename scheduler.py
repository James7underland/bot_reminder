"""
Планировщик напоминаний на APScheduler.

`check_and_send_reminders` — чистая тестируемая логика (БД + отправка
через переданный объект `bot`). `setup_scheduler` — интеграция с
APScheduler (вне unit-тестов).
"""
import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import SCHEDULER_CHECK_INTERVAL
from database import (
    get_due_reminders,
    get_overdue_tasks,
    mark_overdue_notified,
    mark_reminder_sent,
    purge_deleted_lists,
    purge_deleted_notes,
)

logger = logging.getLogger(__name__)

_TIME_FMT = "%Y-%m-%d %H:%M:%S"


async def _notify(bot, tasks, prefix, mark) -> int:
    """Шлёт `prefix: описание` каждой задаче; помечает успешные.

    Анти-дубль: успех → `mark(task_id)`. Ошибка отправки → НЕ помечаем
    (повтор на следующем тике, приоритет — доставить).
    """
    sent = 0
    for task in tasks:
        try:
            await bot.send_message(
                chat_id=task["user_id"],
                text=f"{prefix}: {task['description']}",
            )
        except Exception as e:
            logger.error("notify failed task=%s: %s", task["id"], e)
            continue
        mark(task["id"])
        sent += 1
    return sent


async def check_and_send_reminders(bot, now: datetime | None = None) -> int:
    """
    Шлёт напоминания (наступил `reminder_at`) и уведомления о просрочке
    (прошёл `deadline`). Возвращает общее число отправленных сообщений.

    `now` по умолчанию — текущее UTC (наивная строка; время хранится в
    UTC, Фаза 5.8).
    """
    now = now or datetime.now(UTC).replace(tzinfo=None)
    now_str = now.strftime(_TIME_FMT)
    sent = await _notify(
        bot, get_due_reminders(now_str), "Напоминаю", mark_reminder_sent
    )
    sent += await _notify(
        bot, get_overdue_tasks(now_str), "Просрочено", mark_overdue_notified
    )
    return sent


def _purge_old_soft_deletes() -> None:
    """
    Phase 10.7 + 11.2: раз в час физически удаляет soft-deleted
    списки и заметки старше 24 часов. Каждый purge — в отдельном
    try/except, чтобы ошибка одного не блокировала второй.
    """
    try:
        purge_deleted_lists(older_than_hours=24)
    except Exception as e:
        logger.error("purge_deleted_lists failed: %s", e)
    try:
        purge_deleted_notes(older_than_hours=24)
    except Exception as e:
        logger.error("purge_deleted_notes failed: %s", e)


def setup_scheduler(application) -> AsyncIOScheduler:
    """
    Создаёт планировщик и привязывает его старт/остановку к жизненному
    циклу приложения.

    ВАЖНО: `AsyncIOScheduler.start()` требует уже работающего event loop.
    Если вызвать его прямо в `main()` (до `run_polling`), будет
    `RuntimeError: no running event loop`. Поэтому старт переносится в
    `post_init` (PTB вызывает его внутри запущенного loop), а остановка —
    в `post_shutdown` (graceful).
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_send_reminders,
        trigger="interval",
        seconds=SCHEDULER_CHECK_INTERVAL,
        args=[application.bot],
        id="reminders",
        replace_existing=True,
    )
    # Phase 10.7: раз в час чистим soft-deleted списки старше 24 ч.
    scheduler.add_job(
        _purge_old_soft_deletes,
        trigger="interval",
        hours=1,
        id="purge_deleted",
        replace_existing=True,
    )

    async def _start(_app) -> None:
        scheduler.start()
        logger.info(
            "Планировщик запущен (интервал %s c).", SCHEDULER_CHECK_INTERVAL
        )

    async def _stop(_app) -> None:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("Планировщик остановлен.")

    application.post_init = _start
    application.post_shutdown = _stop
    return scheduler

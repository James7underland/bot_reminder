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
from database import get_due_tasks, mark_reminder_sent

logger = logging.getLogger(__name__)

_TIME_FMT = "%Y-%m-%d %H:%M:%S"


async def check_and_send_reminders(bot, now: datetime | None = None) -> int:
    """
    Находит задачи с наступившим `due_date` и шлёт напоминание.

    Возвращает число успешно отправленных. Анти-дубль: после успешной
    отправки задача помечается `reminder_sent=1`, поэтому повторный вызов
    её не возьмёт. При ошибке отправки задача НЕ помечается — повтор на
    следующем тике (приоритет — доставить напоминание).

    `now` по умолчанию — текущее UTC (наивная строка), т.к. `due_date`
    хранится в UTC (Фаза 5.8).
    """
    now = now or datetime.now(UTC).replace(tzinfo=None)
    now_str = now.strftime(_TIME_FMT)
    sent = 0
    for task in get_due_tasks(now_str):
        try:
            await bot.send_message(
                chat_id=task["user_id"],
                text=f"Напоминаю: {task['description']}",
            )
        except Exception as e:
            logger.error("reminder send failed task=%s: %s", task["id"], e)
            continue
        mark_reminder_sent(task["id"])
        sent += 1
    return sent


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

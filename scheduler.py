"""
Планировщик напоминаний на APScheduler.

`check_and_send_reminders` – чистая тестируемая логика (БД + отправка
через переданный объект `bot`). `setup_scheduler` – интеграция с
APScheduler (вне unit-тестов).
"""
import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from config import SCHEDULER_CHECK_INTERVAL
from database import (
    enqueue_notification,
    get_due_reminders,
    get_overdue_tasks,
    mark_overdue_notified,
    mark_reminder_sent,
    purge_deleted_lists,
    purge_deleted_notes,
    purge_deleted_tasks,
)
from pushsend import send_push_to_user

logger = logging.getLogger(__name__)

_TIME_FMT = "%Y-%m-%d %H:%M:%S"


def _task_text(item) -> str:
    """Текст уведомления для задачи: `описание`."""
    return str(item.get("description") or "")


def _item_channels(item) -> list[str]:
    """Phase 13.1: каналы доставки задачи из CSV-поля (default 'tg')."""
    raw = item.get("reminder_channels") if isinstance(item, dict) \
        else item["reminder_channels"] if "reminder_channels" in item.keys() else None
    if not raw:
        return ["tg"]
    return [c for c in str(raw).split(",") if c]


async def _notify(bot, items, prefix, mark, *, text_for=_task_text) -> int:
    """Шлёт `prefix: текст(item)` по каналам, выбранным на задаче,
    и помечает обработанные. Channels (Phase 13.1):
    - "tg": Telegram-сообщение от бота (как было раньше).
    - "app": усиленное уведомление через Web Push + foreground-queue.
    - "alarm": то же что app, но `requireInteraction=true` + сильная
      вибрация на клиенте.

    Анти-дубль: успех ИЛИ скип (allowlist) → `mark(item.id)`. Полный
    провал по сети — НЕ помечаем, повторяем на следующем тике.

    Phase 11.3: ALLOWED_USER_IDS фильтрует чужие user_id.
    Phase 11.23 (#7): без inline-кнопок в TG-сообщении.
    """
    allowed_ids = config.ALLOWED_USER_IDS
    sent = 0
    for item in items:
        if allowed_ids and item["user_id"] not in allowed_ids:
            mark(item["id"])
            continue
        channels = _item_channels(item)
        text = text_for(item)
        message = f"{prefix}: {text}"
        any_delivered = False
        # --- TG ---
        if "tg" in channels:
            try:
                await bot.send_message(
                    chat_id=item["user_id"], text=message,
                )
                any_delivered = True
            except Exception as e:
                logger.error("tg notify failed item=%s: %s", item["id"], e)
        # --- app/alarm (Web Push + foreground queue) ---
        for ch in ("app", "alarm"):
            if ch not in channels:
                continue
            try:
                enqueue_notification(
                    user_id=item["user_id"],
                    task_id=item["id"],
                    channel=ch,
                    kind=prefix,
                    description=text,
                )
                # Push отдельно — он может тихо не работать (нет VAPID).
                send_push_to_user(
                    user_id=item["user_id"],
                    title=f"{prefix}: {text}",
                    body=text,
                    channel=ch,
                    task_id=item["id"],
                )
                any_delivered = True
            except Exception as e:
                logger.error(
                    "%s notify failed item=%s: %s", ch, item["id"], e,
                )
        if any_delivered or not channels:
            mark(item["id"])
            if any_delivered:
                sent += 1
    return sent


async def check_and_send_reminders(bot, now: datetime | None = None) -> int:
    """
    Шлёт напоминания (наступил `reminder_at`) и уведомления о просрочке
    (прошёл `deadline`). Возвращает общее число обработанных задач.

    `now` по умолчанию – текущее UTC (наивная строка; время хранится в
    UTC, Фаза 5.8). Phase 13.1: маршрутизация по каналам см. `_notify`.
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
    Phase 10.7 + 11.2 + 11.10: раз в час физически удаляет soft-deleted
    списки, заметки и задачи старше 24 часов. Каждый purge – в
    отдельном try/except, чтобы ошибка одного не блокировала остальные.
    """
    try:
        purge_deleted_lists(older_than_hours=24)
    except Exception as e:
        logger.error("purge_deleted_lists failed: %s", e)
    try:
        purge_deleted_notes(older_than_hours=24)
    except Exception as e:
        logger.error("purge_deleted_notes failed: %s", e)
    try:
        purge_deleted_tasks(older_than_hours=24)
    except Exception as e:
        logger.error("purge_deleted_tasks failed: %s", e)


def setup_scheduler(application) -> AsyncIOScheduler:
    """
    Создаёт планировщик и привязывает его старт/остановку к жизненному
    циклу приложения.

    ВАЖНО: `AsyncIOScheduler.start()` требует уже работающего event loop.
    Если вызвать его прямо в `main()` (до `run_polling`), будет
    `RuntimeError: no running event loop`. Поэтому старт переносится в
    `post_init` (PTB вызывает его внутри запущенного loop), а остановка –
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

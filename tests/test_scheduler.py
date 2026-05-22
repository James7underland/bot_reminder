"""Тесты планировщика напоминаний (БД реальная temp, Telegram замокан)."""
import sqlite3
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import database
import scheduler
from database import (
    add_task,
    get_due_reminders,
    get_due_tasks,
    get_overdue_tasks,
    mark_reminder_sent,
    mark_task_done,
    set_deadline,
    set_reminder_at,
)
from scheduler import check_and_send_reminders

NOW = "2026-05-17 12:00:00"
PAST = "2026-05-17 11:00:00"
FUTURE = "2026-05-17 13:00:00"
NOW_DT = datetime(2026, 5, 17, 12, 0, 0)


def test_get_due_tasks_selects_only_due_active_unsent():
    due = add_task(1, "due", PAST)
    add_task(1, "future", FUTURE)
    add_task(1, "no date")
    done = add_task(1, "done", PAST)
    mark_task_done(done)
    already = add_task(1, "already", PAST)
    mark_reminder_sent(already)

    rows = get_due_tasks(NOW)

    assert [r["id"] for r in rows] == [due]
    assert rows[0]["description"] == "due"


def test_get_due_tasks_boundary_is_inclusive():
    tid = add_task(1, "exactly now", NOW)
    assert [r["id"] for r in get_due_tasks(NOW)] == [tid]


def test_mark_reminder_sent_nonexistent_returns_false():
    assert mark_reminder_sent(999999) is False


async def test_check_and_send_reminder_and_idempotent():
    t = add_task(42, "Позвонить врачу")
    set_reminder_at(t, PAST)
    bot = AsyncMock()

    sent = await check_and_send_reminders(bot, now=NOW_DT)

    assert sent == 1
    bot.send_message.assert_awaited_once()
    call = bot.send_message.call_args
    assert call.kwargs["chat_id"] == 42
    assert call.kwargs["text"] == "Напоминаю: Позвонить врачу"
    # Phase 11.23 (#7): уведомление приходит простым текстом, без кнопок.
    assert call.kwargs.get("reply_markup") is None

    bot.reset_mock()
    assert await check_and_send_reminders(bot, now=NOW_DT) == 0
    bot.send_message.assert_not_awaited()
    assert get_due_reminders(NOW) == []


async def test_check_and_send_skips_future_reminder():
    t = add_task(7, "later")
    set_reminder_at(t, FUTURE)
    bot = AsyncMock()

    assert await check_and_send_reminders(bot, now=NOW_DT) == 0
    bot.send_message.assert_not_awaited()


async def test_check_and_send_reminder_failure_not_marked():
    t = add_task(9, "task")
    set_reminder_at(t, PAST)
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("telegram down")

    sent = await check_and_send_reminders(bot, now=NOW_DT)

    assert sent == 0
    assert len(get_due_reminders(NOW)) == 1  # не помечена → повтор


async def test_check_and_send_overdue_and_idempotent():
    t = add_task(5, "Сдать отчёт")
    set_deadline(t, PAST)
    bot = AsyncMock()

    sent = await check_and_send_reminders(bot, now=NOW_DT)

    assert sent == 1
    bot.send_message.assert_awaited_once()
    call = bot.send_message.call_args
    assert call.kwargs["chat_id"] == 5
    assert call.kwargs["text"] == "Просрочено: Сдать отчёт"
    # Phase 11.23 (#7): overdue тоже без inline-кнопок.
    assert call.kwargs.get("reply_markup") is None

    bot.reset_mock()
    assert await check_and_send_reminders(bot, now=NOW_DT) == 0
    bot.send_message.assert_not_awaited()
    assert get_overdue_tasks(NOW) == []


async def test_check_and_send_reminder_and_overdue_together():
    t = add_task(8, "Двойная")
    set_reminder_at(t, PAST)
    set_deadline(t, PAST)
    bot = AsyncMock()

    sent = await check_and_send_reminders(bot, now=NOW_DT)

    assert sent == 2  # и напоминание, и просрочка
    texts = {c.kwargs["text"] for c in bot.send_message.await_args_list}
    assert texts == {"Напоминаю: Двойная", "Просрочено: Двойная"}


def test_init_db_migrates_legacy_table(tmp_path):
    """init_db добавляет reminder_sent в БД, созданную до Фазы 4."""
    legacy = tmp_path / "legacy.db"
    conn = sqlite3.connect(legacy)
    conn.execute(
        "CREATE TABLE tasks ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
        "description TEXT NOT NULL, due_date TEXT, "
        "completed BOOLEAN DEFAULT FALSE, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()

    with patch.object(database, "DATABASE_PATH", str(legacy)):
        database.init_db()

    check = sqlite3.connect(legacy)
    cols = {row[1] for row in check.execute("PRAGMA table_info(tasks)")}
    check.close()
    assert "reminder_sent" in cols


# --- setup_scheduler: регрессия бага «no running event loop» ---

async def test_setup_scheduler_defers_start_to_post_init():
    fake = MagicMock()
    fake.running = True
    app = MagicMock()
    app.bot = object()
    with patch.object(scheduler, "AsyncIOScheduler", return_value=fake):
        result = scheduler.setup_scheduler(app)
    assert result is fake
    # С Phase 10.7 – два job'а: reminders + purge_deleted.
    assert fake.add_job.call_count == 2
    job_ids = {call.kwargs.get("id") for call in fake.add_job.call_args_list}
    assert job_ids == {"reminders", "purge_deleted"}
    # НЕ стартует синхронно – это и был прод-баг "no running event loop"
    fake.start.assert_not_called()
    # старт/стоп навешаны на жизненный цикл приложения
    await app.post_init(app)
    fake.start.assert_called_once()
    await app.post_shutdown(app)
    fake.shutdown.assert_called_once()


def test_purge_job_wrapper_swallows_errors(monkeypatch, caplog):
    """`_purge_old_soft_deletes` логирует ошибку, но НЕ кидает –
    иначе APScheduler пометит job сломанным и в худшем случае
    перестанет запускать. Phase 11.2: и для lists, и для notes."""
    import scheduler as scheduler_mod

    def boom_lists(**kw):
        raise RuntimeError("simulated lists crash")
    def boom_notes(**kw):
        raise RuntimeError("simulated notes crash")
    monkeypatch.setattr(scheduler_mod, "purge_deleted_lists", boom_lists)
    monkeypatch.setattr(scheduler_mod, "purge_deleted_notes", boom_notes)
    with caplog.at_level("ERROR"):
        scheduler_mod._purge_old_soft_deletes()   # не должно падать
    msgs = " ".join(caplog.messages)
    assert "purge_deleted_lists failed" in msgs
    assert "purge_deleted_notes failed" in msgs


async def test_setup_scheduler_stop_skips_when_not_running():
    fake = MagicMock()
    fake.running = False
    app = MagicMock()
    with patch.object(scheduler, "AsyncIOScheduler", return_value=fake):
        scheduler.setup_scheduler(app)
    await app.post_shutdown(app)
    fake.shutdown.assert_not_called()

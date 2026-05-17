"""Тесты планировщика напоминаний (БД реальная temp, Telegram замокан)."""
import sqlite3
from datetime import datetime
from unittest.mock import AsyncMock, patch

import database
from database import add_task, get_due_tasks, mark_reminder_sent, mark_task_done
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


async def test_check_and_send_sends_and_is_idempotent():
    add_task(42, "Позвонить врачу", PAST)
    bot = AsyncMock()

    sent = await check_and_send_reminders(bot, now=NOW_DT)

    assert sent == 1
    bot.send_message.assert_awaited_once_with(
        chat_id=42, text="Напоминаю: Позвонить врачу"
    )

    bot.reset_mock()
    assert await check_and_send_reminders(bot, now=NOW_DT) == 0
    bot.send_message.assert_not_awaited()
    assert get_due_tasks(NOW) == []


async def test_check_and_send_skips_future():
    add_task(7, "later", FUTURE)
    bot = AsyncMock()

    assert await check_and_send_reminders(bot, now=NOW_DT) == 0
    bot.send_message.assert_not_awaited()


async def test_check_and_send_failure_is_not_marked():
    add_task(9, "task", PAST)
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("telegram down")

    sent = await check_and_send_reminders(bot, now=NOW_DT)

    assert sent == 0
    # не помечена → повтор на следующем тике
    assert len(get_due_tasks(NOW)) == 1


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

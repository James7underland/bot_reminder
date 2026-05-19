"""Фаза 7.1: модель «срок» (deadline) vs «напоминание» (reminder_at)."""
import sqlite3
from unittest.mock import patch

import database
from database import (
    add_task,
    get_due_reminders,
    get_overdue_tasks,
    get_task,
    mark_overdue_notified,
    mark_reminder_sent,
    mark_task_done,
    set_deadline,
    set_reminder_at,
)

NOW = "2026-05-19 12:00:00"
PAST = "2026-05-19 11:00:00"
FUTURE = "2026-05-19 13:00:00"


# --- миграция legacy ---

def test_migration_copies_due_date_to_reminder_at(tmp_path):
    legacy = tmp_path / "legacy.db"
    conn = sqlite3.connect(legacy)
    conn.execute(
        "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER NOT NULL, description TEXT NOT NULL, due_date TEXT, "
        "completed BOOLEAN DEFAULT FALSE, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "INSERT INTO tasks (user_id, description, due_date) "
        "VALUES (1, 'old', '2026-05-19 09:00:00')"
    )
    conn.commit()
    conn.close()

    with patch.object(database, "DATABASE_PATH", str(legacy)):
        database.init_db()

    check = sqlite3.connect(legacy)
    cols = {r[1] for r in check.execute("PRAGMA table_info(tasks)")}
    row = check.execute(
        "SELECT reminder_at, deadline, overdue_notified FROM tasks"
    ).fetchone()
    check.close()
    assert {"deadline", "reminder_at", "overdue_notified"} <= cols
    assert row[0] == "2026-05-19 09:00:00"  # due_date -> reminder_at
    assert row[1] is None                    # deadline пуст
    assert row[2] == 0


# --- set_deadline / set_reminder_at ---

def test_set_deadline_lifecycle_and_resets_overdue():
    tid = add_task(1, "t")
    assert set_deadline(tid, PAST) is True
    assert get_task(tid)["deadline"] == PAST
    # пометили как уведомлённую о просрочке
    assert mark_overdue_notified(tid) is True
    assert get_task(tid)["overdue_notified"] == 1
    # новый срок сбрасывает overdue_notified
    assert set_deadline(tid, FUTURE) is True
    assert get_task(tid)["overdue_notified"] == 0
    assert set_deadline(tid, None) is True
    assert get_task(tid)["deadline"] is None
    assert set_deadline(999999, PAST) is False


def test_set_reminder_at_lifecycle_and_resets_sent():
    tid = add_task(1, "t")
    assert set_reminder_at(tid, PAST) is True
    assert get_task(tid)["reminder_at"] == PAST
    mark_reminder_sent(tid)
    assert get_task(tid)["reminder_sent"] == 1
    assert set_reminder_at(tid, FUTURE) is True       # сброс reminder_sent
    assert get_task(tid)["reminder_sent"] == 0
    assert set_reminder_at(tid, None) is True
    assert get_task(tid)["reminder_at"] is None
    assert set_reminder_at(999999, PAST) is False


# --- get_due_reminders ---

def test_get_due_reminders_selects_correctly():
    due = add_task(1, "due")
    set_reminder_at(due, PAST)
    fut = add_task(1, "future")
    set_reminder_at(fut, FUTURE)
    none = add_task(1, "no reminder")
    done = add_task(1, "done")
    set_reminder_at(done, PAST)
    mark_task_done(done)
    sent = add_task(1, "already sent")
    set_reminder_at(sent, PAST)
    mark_reminder_sent(sent)

    ids = [t["id"] for t in get_due_reminders(NOW)]
    assert ids == [due]
    assert none  # silence linter on unused var intent


# --- get_overdue_tasks ---

def test_get_overdue_tasks_selects_correctly():
    overdue = add_task(1, "overdue")
    set_deadline(overdue, PAST)
    not_yet = add_task(1, "not yet")
    set_deadline(not_yet, FUTURE)
    no_dl = add_task(1, "no deadline")
    done = add_task(1, "done overdue")
    set_deadline(done, PAST)
    mark_task_done(done)
    notified = add_task(1, "already notified")
    set_deadline(notified, PAST)
    mark_overdue_notified(notified)

    ids = [t["id"] for t in get_overdue_tasks(NOW)]
    assert ids == [overdue]
    assert no_dl


def test_overdue_boundary_strictly_after():
    t = add_task(1, "exactly now deadline")
    set_deadline(t, NOW)
    # ровно в срок ещё НЕ просрочено
    assert get_overdue_tasks(NOW) == []
    assert [x["id"] for x in get_overdue_tasks("2026-05-19 12:00:01")] == [t]


def test_mark_overdue_notified_nonexistent():
    assert mark_overdue_notified(999999) is False

"""Фаза 5.6: тесты «Мой день» (БД-слой).

С Phase 11.1 чат-команды убраны. Сценарии My Day в Mini App – в
`test_webapp.py`.
"""
import sqlite3
from unittest.mock import patch

import database
from database import (
    add_task,
    add_to_myday,
    get_myday,
    mark_task_done,
    remove_from_myday,
)

DAY = "2026-05-17"
OTHER = "2026-05-18"


# --- слой БД ---

def test_add_remove_myday():
    tid = add_task(1, "t")
    assert add_to_myday(tid, DAY) is True
    assert [t["id"] for t in get_myday(1, DAY)] == [tid]
    assert remove_from_myday(tid) is True
    assert get_myday(1, DAY) == []
    assert add_to_myday(999999, DAY) is False
    assert remove_from_myday(999999) is False


def test_get_myday_includes_due_today_excludes_others():
    due_today = add_task(1, "due today", f"{DAY} 09:00:00")
    add_task(1, "due tomorrow", f"{OTHER} 09:00:00")
    add_task(1, "no due, not pinned")
    done = add_task(1, "done today", f"{DAY} 10:00:00")
    mark_task_done(done)

    ids = [t["id"] for t in get_myday(1, DAY)]
    assert ids == [due_today]


def test_get_myday_orders_due_before_pinned():
    pinned = add_task(1, "pinned no due")
    add_to_myday(pinned, DAY)
    due = add_task(1, "due today", f"{DAY} 08:00:00")

    ids = [t["id"] for t in get_myday(1, DAY)]
    assert ids == [due, pinned]


def test_init_db_migrates_myday(tmp_path):
    legacy = tmp_path / "legacy.db"
    conn = sqlite3.connect(legacy)
    conn.execute(
        "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER NOT NULL, description TEXT NOT NULL, due_date TEXT, "
        "completed BOOLEAN DEFAULT FALSE, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.commit()
    conn.close()
    with patch.object(database, "DATABASE_PATH", str(legacy)):
        database.init_db()
    check = sqlite3.connect(legacy)
    cols = {r[1] for r in check.execute("PRAGMA table_info(tasks)")}
    check.close()
    assert "myday_date" in cols



"""Фаза 5.5: тесты подзадач (steps) и заметок (notes) – БД-слой.

С Phase 11.1 чат-команды убраны.
"""
import sqlite3
from unittest.mock import patch

import database
from database import (
    add_step,
    add_task,
    delete_step,
    get_steps,
    get_task,
    mark_step_done,
    set_note,
)

# --- слой БД ---

def test_add_step_and_get_steps():
    tid = add_task(1, "parent")
    s1 = add_step(tid, "step one")
    s2 = add_step(tid, "step two")
    assert isinstance(s1, int) and isinstance(s2, int)
    steps = get_steps(tid)
    assert [s["id"] for s in steps] == [s1, s2]
    assert steps[0]["description"] == "step one"
    assert steps[0]["completed"] is False


def test_add_step_missing_task_returns_none():
    assert add_step(999999, "x") is None


def test_mark_step_done_toggle_and_missing():
    tid = add_task(1, "p")
    sid = add_step(tid, "s")
    assert mark_step_done(sid, True) is True
    assert get_steps(tid)[0]["completed"] is True
    assert mark_step_done(sid, False) is True
    assert get_steps(tid)[0]["completed"] is False
    assert mark_step_done(999999, True) is False


def test_delete_step():
    tid = add_task(1, "p")
    sid = add_step(tid, "s")
    assert delete_step(sid) is True
    assert get_steps(tid) == []
    assert delete_step(999999) is False


def test_get_task_and_set_note():
    tid = add_task(1, "p")
    task = get_task(tid)
    assert task["description"] == "p"
    assert task["completed"] is False and task["important"] is False
    assert task["notes"] is None

    assert set_note(tid, "важная заметка") is True
    assert get_task(tid)["notes"] == "важная заметка"
    assert set_note(tid, None) is True
    assert get_task(tid)["notes"] is None
    assert set_note(999999, "x") is False


def test_get_task_missing_returns_none():
    assert get_task(999999) is None


def test_init_db_migrates_notes_and_steps(tmp_path):
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
    tables = {
        r[0]
        for r in check.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    check.close()
    assert "notes" in cols
    assert "steps" in tables

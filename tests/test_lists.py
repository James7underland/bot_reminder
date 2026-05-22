"""Фаза 5.2: тесты списков/категорий (БД, миграция).

С Phase 11.1 чат-команды убраны – соответствующие тесты тоже. Слой БД
покрывается этим файлом; пользовательские сценарии – в `test_webapp.py`.
"""
import sqlite3
from unittest.mock import patch

import database
from database import (
    add_task,
    assign_task_to_list,
    create_list,
    delete_list,
    get_lists,
    get_tasks_by_list,
    mark_task_done,
    rename_list,
)

# --- слой БД ---

def test_create_and_get_lists():
    lid = create_list(1, "Работа")
    assert isinstance(lid, int) and lid > 0
    lists = get_lists(1)
    assert len(lists) == 1
    assert lists[0]["name"] == "Работа" and lists[0]["user_id"] == 1


def test_get_lists_isolated_per_user_and_empty():
    create_list(1, "A")
    assert get_lists(2) == []


def test_rename_list():
    lid = create_list(1, "Old")
    assert rename_list(lid, "New") is True
    assert get_lists(1)[0]["name"] == "New"
    assert rename_list(999999, "X") is False


def test_delete_list_is_soft_with_undo_window():
    """
    Phase 10.7: delete_list – soft. Список скрывается из get_lists,
    но задачи СОХРАНЯЮТ list_id (на время undo-окна). Hard-удаление –
    через `purge_deleted_lists` после 24 часов.
    """
    lid = create_list(1, "L")
    tid = add_task(1, "task")
    assign_task_to_list(tid, lid)
    assert [t["id"] for t in get_tasks_by_list(1, lid)] == [tid]

    assert delete_list(lid) is True
    # Из get_lists() (видимых) – исчез
    assert get_lists(1) == []
    # С include_deleted=True – виден, deleted_at заполнен
    all_lists = get_lists(1, include_deleted=True)
    assert len(all_lists) == 1
    assert all_lists[0]["deleted_at"] is not None
    # Задача сохранила привязку – не переехала в «без списка»
    assert [t["id"] for t in get_tasks_by_list(1, None)] == []
    assert [t["id"] for t in get_tasks_by_list(1, lid)] == [tid]
    # Повторный delete (уже удалённого) → False
    assert delete_list(lid) is False
    # Несуществующий → False
    assert delete_list(999999) is False


def test_assign_task_to_list_and_filters():
    lid = create_list(1, "L")
    t1 = add_task(1, "in list")
    t2 = add_task(1, "no list")
    assert assign_task_to_list(t1, lid) is True

    assert [t["id"] for t in get_tasks_by_list(1, lid)] == [t1]
    assert [t["id"] for t in get_tasks_by_list(1, None)] == [t2]

    # completed исключается по умолчанию
    mark_task_done(t1)
    assert get_tasks_by_list(1, lid) == []
    assert [t["id"] for t in get_tasks_by_list(1, lid, completed=True)] == [t1]

    assert assign_task_to_list(999999, lid) is False


def test_assign_task_to_none_removes_from_list():
    lid = create_list(1, "L")
    tid = add_task(1, "t")
    assign_task_to_list(tid, lid)
    assert assign_task_to_list(tid, None) is True
    assert [t["id"] for t in get_tasks_by_list(1, None)] == [tid]


# --- миграция legacy-БД ---

def test_init_db_migrates_legacy_to_lists(tmp_path):
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
    task_cols = {r[1] for r in check.execute("PRAGMA table_info(tasks)")}
    tables = {
        r[0] for r in check.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    check.close()
    assert "list_id" in task_cols
    assert "reminder_sent" in task_cols
    assert "lists" in tables

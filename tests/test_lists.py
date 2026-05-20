"""Фаза 5.2: тесты списков/категорий (БД, хендлеры, миграция)."""
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import bot
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


def make_update(user_id=42):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    return update


def make_context(args):
    ctx = MagicMock()
    ctx.args = args
    return ctx


def reply(update):
    return update.message.reply_text.call_args.args[0]


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
    Phase 10.7: delete_list — soft. Список скрывается из get_lists,
    но задачи СОХРАНЯЮТ list_id (на время undo-окна). Hard-удаление —
    через `purge_deleted_lists` после 24 часов.
    """
    lid = create_list(1, "L")
    tid = add_task(1, "task")
    assign_task_to_list(tid, lid)
    assert [t["id"] for t in get_tasks_by_list(1, lid)] == [tid]

    assert delete_list(lid) is True
    # Из get_lists() (видимых) — исчез
    assert get_lists(1) == []
    # С include_deleted=True — виден, deleted_at заполнен
    all_lists = get_lists(1, include_deleted=True)
    assert len(all_lists) == 1
    assert all_lists[0]["deleted_at"] is not None
    # Задача сохранила привязку — не переехала в «без списка»
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


# --- хендлеры списков ---

async def test_lists_empty():
    u = make_update()
    with patch.object(bot, "get_lists", return_value=[]):
        await bot.lists_command(u, make_context([]))
    assert "нет списков" in reply(u).lower()


async def test_lists_shows_items():
    u = make_update()
    with patch.object(bot, "get_lists", return_value=[{"id": 3, "name": "Дом"}]):
        await bot.lists_command(u, make_context([]))
    assert "Дом" in reply(u) and "3" in reply(u)


async def test_newlist_no_args():
    u = make_update()
    await bot.newlist_command(u, make_context([]))
    assert "Использование" in reply(u)


async def test_newlist_success():
    u = make_update()
    with patch.object(bot, "create_list", return_value=9) as m:
        await bot.newlist_command(u, make_context(["Мой", "список"]))
    m.assert_called_once_with(42, "Мой список")
    assert "создан" in reply(u).lower()


async def test_renamelist_validation_and_success():
    u = make_update()
    await bot.renamelist_command(u, make_context(["7"]))
    assert "Использование" in reply(u)

    u = make_update()
    await bot.renamelist_command(u, make_context(["abc", "n"]))
    assert "числом" in reply(u).lower()

    u = make_update()
    await bot.renamelist_command(u, make_context(["7", ""]))
    assert "имя" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "rename_list", return_value=True):
        await bot.renamelist_command(u, make_context(["7", "Новое"]))
    assert "переименован" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "rename_list", return_value=False):
        await bot.renamelist_command(u, make_context(["7", "Новое"]))
    assert "не найден" in reply(u).lower()


async def test_dellist_validation_and_success():
    u = make_update()
    await bot.dellist_command(u, make_context([]))
    assert "Использование" in reply(u)

    u = make_update()
    await bot.dellist_command(u, make_context(["abc"]))
    assert "числом" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "delete_list", return_value=True):
        await bot.dellist_command(u, make_context(["7"]))
    assert "удалён" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "delete_list", return_value=False):
        await bot.dellist_command(u, make_context(["7"]))
    assert "не найден" in reply(u).lower()


async def test_movetask_validation():
    u = make_update()
    await bot.movetask_command(u, make_context(["7"]))
    assert "Использование" in reply(u)

    u = make_update()
    await bot.movetask_command(u, make_context(["abc", "1"]))
    assert "числами" in reply(u).lower()


async def test_movetask_list_not_found():
    u = make_update()
    with patch.object(bot, "get_lists", return_value=[]):
        await bot.movetask_command(u, make_context(["7", "9"]))
    assert "Список №9 не найден" in reply(u)


async def test_movetask_success_to_list():
    u = make_update()
    with patch.object(bot, "get_lists", return_value=[{"id": 3, "name": "X"}]), \
         patch.object(bot, "assign_task_to_list", return_value=True) as m:
        await bot.movetask_command(u, make_context(["7", "3"]))
    m.assert_called_once_with(7, 3)
    assert "в список №3" in reply(u)


async def test_movetask_success_to_no_list():
    u = make_update()
    with patch.object(bot, "assign_task_to_list", return_value=True) as m:
        await bot.movetask_command(u, make_context(["7", "0"]))
    m.assert_called_once_with(7, None)
    assert "без списка" in reply(u).lower()


async def test_movetask_task_not_found():
    u = make_update()
    with patch.object(bot, "assign_task_to_list", return_value=False):
        await bot.movetask_command(u, make_context(["7", "0"]))
    assert "Задача №7 не найдена" in reply(u)


# --- /list с фильтром по списку ---

async def test_list_filter_bad_id():
    u = make_update()
    await bot.list_tasks(u, make_context(["abc"]))
    assert "ID списка" in reply(u)


async def test_list_filter_by_list_id():
    u = make_update()
    tasks = [{"id": 1, "description": "A", "due_date": None}]
    with patch.object(bot, "get_tasks_by_list", return_value=tasks) as m:
        await bot.list_tasks(u, make_context(["3"]))
    m.assert_called_once_with(42, 3)
    assert "списка №3" in reply(u)


async def test_list_filter_no_list():
    u = make_update()
    with patch.object(bot, "get_tasks_by_list", return_value=[]) as m:
        await bot.list_tasks(u, make_context(["0"]))
    m.assert_called_once_with(42, None)
    assert "нет активных" in reply(u).lower()


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

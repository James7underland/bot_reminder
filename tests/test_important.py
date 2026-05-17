"""Фаза 5.4: тесты важных задач и сортировок."""
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import bot
import database
from database import add_task, get_tasks, set_important


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

def test_set_important_lifecycle():
    tid = add_task(1, "t")
    assert get_tasks(1)[0]["important"] is False
    assert set_important(tid, True) is True
    assert get_tasks(1)[0]["important"] is True
    assert set_important(tid, False) is True
    assert get_tasks(1)[0]["important"] is False


def test_set_important_nonexistent():
    assert set_important(999999, True) is False


def test_sort_important_first():
    a = add_task(1, "plain")
    b = add_task(1, "starred")
    set_important(b, True)
    ordered = [t["id"] for t in get_tasks(1, sort="important")]
    assert ordered == [b, a]


def test_sort_alpha_case_insensitive():
    add_task(1, "banana")
    add_task(1, "Apple")
    add_task(1, "cherry")
    names = [t["description"] for t in get_tasks(1, sort="alpha")]
    assert names == ["Apple", "banana", "cherry"]


def test_sort_due_nulls_last():
    a = add_task(1, "no due")
    b = add_task(1, "early", "2026-01-01 00:00:00")
    c = add_task(1, "late", "2026-06-01 00:00:00")
    ordered = [t["id"] for t in get_tasks(1, sort="due")]
    assert ordered == [b, c, a]


def test_default_sort_unchanged_is_created_order():
    x = add_task(1, "x")
    y = add_task(1, "y")
    assert [t["id"] for t in get_tasks(1)] == [x, y]


def test_init_db_migrates_important(tmp_path):
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
    assert "important" in cols


# --- хендлеры ---

async def test_important_no_args():
    u = make_update()
    await bot.important_command(u, make_context([]))
    assert "/important" in reply(u)


async def test_important_non_int():
    u = make_update()
    await bot.important_command(u, make_context(["abc"]))
    assert "числом" in reply(u).lower()


async def test_important_success():
    u = make_update()
    with patch.object(bot, "set_important", return_value=True) as m:
        await bot.important_command(u, make_context(["5"]))
    m.assert_called_once_with(5, True)
    assert "важной" in reply(u).lower()


async def test_important_not_found():
    u = make_update()
    with patch.object(bot, "set_important", return_value=False):
        await bot.important_command(u, make_context(["5"]))
    assert "не найдена" in reply(u).lower()


async def test_unimportant_usage_and_success():
    u = make_update()
    await bot.unimportant_command(u, make_context([]))
    assert "/unimportant" in reply(u)

    u = make_update()
    with patch.object(bot, "set_important", return_value=True) as m:
        await bot.unimportant_command(u, make_context(["5"]))
    m.assert_called_once_with(5, False)
    assert "снята" in reply(u).lower()


async def test_list_sort_keyword():
    u = make_update()
    tasks = [{"id": 1, "description": "A", "due_date": None}]
    with patch.object(bot, "get_tasks", return_value=tasks) as m:
        await bot.list_tasks(u, make_context(["important"]))
    m.assert_called_once_with(42, sort="important")
    assert "сортировка: important" in reply(u)


async def test_list_marks_important():
    u = make_update()
    tasks = [{"id": 1, "description": "X", "due_date": None, "important": True}]
    with patch.object(bot, "get_tasks", return_value=tasks):
        await bot.list_tasks(u, make_context([]))
    assert "[важно] X" in reply(u)

"""Фаза 5.6: тесты «Мой день»."""
import sqlite3
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import bot
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


# --- хендлеры ---

async def test_myday_list_empty():
    u = make_update()
    with patch.object(bot, "get_myday", return_value=[]):
        await bot.myday_command(u, make_context([]))
    assert "ничего нет" in reply(u).lower()


async def test_myday_list_renders():
    u = make_update()
    tasks = [
        {"id": 1, "description": "A", "due_date": "2026-05-17 09:00:00",
         "important": True},
        {"id": 2, "description": "B", "due_date": None, "important": False},
    ]
    with patch.object(bot, "get_myday", return_value=tasks):
        await bot.myday_command(u, make_context([]))
    out = reply(u)
    assert "Мой день:" in out
    assert "[важно] A" in out and "2026-05-17 09:00:00" in out
    assert "2. B" in out


async def test_myday_add_success():
    u = make_update()
    with patch.object(bot, "add_to_myday", return_value=True) as m:
        await bot.myday_command(u, make_context(["add", "7"]))
    m.assert_called_once_with(7, ANY)
    assert "добавлена" in reply(u).lower()


async def test_myday_add_not_found():
    u = make_update()
    with patch.object(bot, "add_to_myday", return_value=False):
        await bot.myday_command(u, make_context(["add", "7"]))
    assert "не найдена" in reply(u).lower()


async def test_myday_remove_and_alias():
    u = make_update()
    with patch.object(bot, "remove_from_myday", return_value=True) as m:
        await bot.myday_command(u, make_context(["remove", "7"]))
    m.assert_called_once_with(7)
    assert "убрана" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "remove_from_myday", return_value=True) as m:
        await bot.myday_command(u, make_context(["rm", "9"]))
    m.assert_called_once_with(9)


async def test_myday_subcommand_validation():
    u = make_update()
    await bot.myday_command(u, make_context(["add"]))
    assert "Использование" in reply(u)

    u = make_update()
    await bot.myday_command(u, make_context(["add", "abc"]))
    assert "числом" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "remove_from_myday", return_value=False):
        await bot.myday_command(u, make_context(["remove", "7"]))
    assert "не найдена" in reply(u).lower()

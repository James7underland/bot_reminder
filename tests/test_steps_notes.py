"""Фаза 5.5: тесты подзадач (steps) и заметок (notes)."""
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import bot
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


# --- хендлеры подзадач ---

async def test_addstep_validation():
    u = make_update()
    await bot.addstep_command(u, make_context(["7"]))
    assert "Использование" in reply(u)

    u = make_update()
    await bot.addstep_command(u, make_context(["abc", "x"]))
    assert "числом" in reply(u).lower()

    u = make_update()
    await bot.addstep_command(u, make_context(["7", "  "]))
    assert "подзадач" in reply(u).lower()


async def test_addstep_success_and_missing():
    u = make_update()
    with patch.object(bot, "add_step", return_value=11) as m:
        await bot.addstep_command(u, make_context(["7", "купить", "хлеб"]))
    m.assert_called_once_with(7, "купить хлеб")
    assert "№11" in reply(u)

    u = make_update()
    with patch.object(bot, "add_step", return_value=None):
        await bot.addstep_command(u, make_context(["7", "x"]))
    assert "не найдена" in reply(u).lower()


async def test_steps_command_renders_note_and_steps():
    u = make_update()
    task = {"id": 7, "description": "P", "notes": "помни"}
    steps = [
        {"id": 1, "description": "a", "completed": True},
        {"id": 2, "description": "b", "completed": False},
    ]
    with patch.object(bot, "get_task", return_value=task), \
         patch.object(bot, "get_steps", return_value=steps):
        await bot.steps_command(u, make_context(["7"]))
    out = reply(u)
    assert "помни" in out and "[x] 1. a" in out and "[ ] 2. b" in out


async def test_steps_command_not_found_and_empty():
    u = make_update()
    with patch.object(bot, "get_task", return_value=None):
        await bot.steps_command(u, make_context(["7"]))
    assert "не найдена" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "get_task", return_value={"id": 7, "description": "P"}), \
         patch.object(bot, "get_steps", return_value=[]):
        await bot.steps_command(u, make_context(["7"]))
    assert "Подзадач нет" in reply(u)


async def test_steps_command_usage_and_non_int():
    u = make_update()
    await bot.steps_command(u, make_context([]))
    assert "Использование" in reply(u)
    u = make_update()
    await bot.steps_command(u, make_context(["abc"]))
    assert "числом" in reply(u).lower()


async def test_stepdone_and_undone():
    u = make_update()
    await bot.stepdone_command(u, make_context([]))
    assert "/stepdone" in reply(u)

    u = make_update()
    with patch.object(bot, "mark_step_done", return_value=True) as m:
        await bot.stepdone_command(u, make_context(["3"]))
    m.assert_called_once_with(3, True)
    assert "выполнена" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "mark_step_done", return_value=True) as m:
        await bot.stepundone_command(u, make_context(["3"]))
    m.assert_called_once_with(3, False)
    assert "активна" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "mark_step_done", return_value=False):
        await bot.stepdone_command(u, make_context(["3"]))
    assert "не найдена" in reply(u).lower()

    u = make_update()
    await bot.stepdone_command(u, make_context(["abc"]))
    assert "числом" in reply(u).lower()


async def test_delstep():
    u = make_update()
    await bot.delstep_command(u, make_context([]))
    assert "Использование" in reply(u)

    u = make_update()
    with patch.object(bot, "delete_step", return_value=True):
        await bot.delstep_command(u, make_context(["3"]))
    assert "удалена" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "delete_step", return_value=False):
        await bot.delstep_command(u, make_context(["3"]))
    assert "не найдена" in reply(u).lower()

    u = make_update()
    await bot.delstep_command(u, make_context(["abc"]))
    assert "числом" in reply(u).lower()


# --- хендлеры заметок ---

async def test_note_view_modes():
    u = make_update()
    await bot.note_command(u, make_context([]))
    assert "Использование" in reply(u)

    u = make_update()
    await bot.note_command(u, make_context(["abc"]))
    assert "числом" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "get_task", return_value=None):
        await bot.note_command(u, make_context(["7"]))
    assert "не найдена" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "get_task", return_value={"id": 7, "notes": "txt"}):
        await bot.note_command(u, make_context(["7"]))
    assert "txt" in reply(u)

    u = make_update()
    with patch.object(bot, "get_task", return_value={"id": 7, "notes": None}):
        await bot.note_command(u, make_context(["7"]))
    assert "нет заметки" in reply(u).lower()


async def test_note_set_and_delnote():
    u = make_update()
    with patch.object(bot, "set_note", return_value=True) as m:
        await bot.note_command(u, make_context(["7", "позвонить", "маме"]))
    m.assert_called_once_with(7, "позвонить маме")
    assert "сохранена" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "set_note", return_value=False):
        await bot.note_command(u, make_context(["7", "x"]))
    assert "не найдена" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "set_note", return_value=True) as m:
        await bot.delnote_command(u, make_context(["7"]))
    m.assert_called_once_with(7, None)
    assert "удалена" in reply(u).lower()

    u = make_update()
    await bot.delnote_command(u, make_context([]))
    assert "Использование" in reply(u)

    u = make_update()
    await bot.delnote_command(u, make_context(["abc"]))
    assert "числом" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "set_note", return_value=False):
        await bot.delnote_command(u, make_context(["7"]))
    assert "не найдена" in reply(u).lower()

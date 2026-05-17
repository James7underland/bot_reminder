"""Фаза 5.1: тесты редактирования / переноса / отмены выполнения."""
from unittest.mock import AsyncMock, MagicMock, patch

import bot
from database import (
    add_task,
    get_tasks,
    mark_task_done,
    mark_task_undone,
    update_task_description,
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

def test_update_task_description_success():
    tid = add_task(1, "old")
    assert update_task_description(tid, "new") is True
    assert get_tasks(1)[0]["description"] == "new"


def test_update_task_description_nonexistent():
    assert update_task_description(999999, "x") is False


def test_mark_task_undone_reactivates():
    tid = add_task(1, "task")
    mark_task_done(tid)
    assert get_tasks(1) == []
    assert mark_task_undone(tid) is True
    active = get_tasks(1)
    assert len(active) == 1 and active[0]["id"] == tid


def test_mark_task_undone_nonexistent():
    assert mark_task_undone(999999) is False


# --- parse_datetime ---

def test_parse_datetime_iso():
    assert bot.parse_datetime("2026-05-18 15:00") == "2026-05-18 15:00:00"


def test_parse_datetime_dotted():
    assert bot.parse_datetime("18.05.2026 09:30") == "2026-05-18 09:30:00"


def test_parse_datetime_invalid():
    assert bot.parse_datetime("завтра утром") is None
    assert bot.parse_datetime("2026-13-40 99:99") is None


# --- /edit ---

async def test_edit_no_args():
    u = make_update()
    await bot.edit_task_command(u, make_context([]))
    assert "Использование" in reply(u)


async def test_edit_non_int_id():
    u = make_update()
    await bot.edit_task_command(u, make_context(["abc", "text"]))
    assert "числом" in reply(u).lower()


async def test_edit_empty_description():
    u = make_update()
    await bot.edit_task_command(u, make_context(["5", ""]))
    assert "описание" in reply(u).lower()


async def test_edit_success():
    u = make_update()
    with patch.object(bot, "update_task_description", return_value=True) as m:
        await bot.edit_task_command(u, make_context(["7", "новое", "описание"]))
    m.assert_called_once_with(7, "новое описание")
    assert "обновлена" in reply(u).lower()


async def test_edit_not_found():
    u = make_update()
    with patch.object(bot, "update_task_description", return_value=False):
        await bot.edit_task_command(u, make_context(["7", "x"]))
    assert "не найдена" in reply(u).lower()


# --- /reschedule ---

async def test_reschedule_no_args():
    u = make_update()
    await bot.reschedule_command(u, make_context(["7"]))
    assert "Использование" in reply(u)


async def test_reschedule_non_int_id():
    u = make_update()
    await bot.reschedule_command(u, make_context(["abc", "2026-05-18", "15:00"]))
    assert "числом" in reply(u).lower()


async def test_reschedule_bad_date():
    u = make_update()
    await bot.reschedule_command(u, make_context(["7", "когда-нибудь"]))
    assert "дату" in reply(u).lower()


async def test_reschedule_success():
    u = make_update()
    with patch.object(bot, "set_reminder", return_value=True) as m:
        await bot.reschedule_command(u, make_context(["7", "2026-05-18", "15:00"]))
    m.assert_called_once_with(7, "2026-05-18 15:00:00")
    assert "перенесено" in reply(u).lower()


async def test_reschedule_not_found():
    u = make_update()
    with patch.object(bot, "set_reminder", return_value=False):
        await bot.reschedule_command(u, make_context(["7", "2026-05-18", "15:00"]))
    assert "не найдена" in reply(u).lower()


# --- /undone ---

async def test_undone_no_args():
    u = make_update()
    await bot.undone_command(u, make_context([]))
    assert "Использование" in reply(u)


async def test_undone_non_int():
    u = make_update()
    await bot.undone_command(u, make_context(["abc"]))
    assert "числом" in reply(u).lower()


async def test_undone_success():
    u = make_update()
    with patch.object(bot, "mark_task_undone", return_value=True) as m:
        await bot.undone_command(u, make_context(["3"]))
    m.assert_called_once_with(3)
    assert "активна" in reply(u).lower()


async def test_undone_not_found():
    u = make_update()
    with patch.object(bot, "mark_task_undone", return_value=False):
        await bot.undone_command(u, make_context(["3"]))
    assert "не найдена" in reply(u).lower()

"""Фаза 5.7: тесты поиска и гибких напоминаний."""
from unittest.mock import AsyncMock, MagicMock, patch

import bot
from database import (
    add_task,
    get_due_tasks,
    get_task,
    mark_task_done,
    search_tasks,
    set_note,
    set_remind_before,
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


# --- search_tasks ---

def test_search_empty_query():
    add_task(1, "что-то")
    assert search_tasks(1, "   ") == []


def test_search_in_description_case_insensitive():
    t = add_task(1, "Купить молоко")
    add_task(1, "Помыть машину")
    assert [x["id"] for x in search_tasks(1, "молоко")] == [t]
    assert [x["id"] for x in search_tasks(1, "МОЛОКО")] == [t]


def test_search_in_notes():
    t = add_task(1, "Задача")
    set_note(t, "позвонить врачу завтра")
    assert [x["id"] for x in search_tasks(1, "врач")] == [t]


def test_search_excludes_completed_and_other_users():
    done = add_task(1, "найди меня done")
    mark_task_done(done)
    add_task(2, "найди меня other")
    assert search_tasks(1, "найди меня") == []


# --- set_remind_before ---

def test_set_remind_before_lifecycle():
    t = add_task(1, "t", "2026-05-17 12:00:00")
    assert set_remind_before(t, 30) is True
    assert get_task(t)["remind_before"] == 30
    assert set_remind_before(t, None) is True
    assert get_task(t)["remind_before"] is None


def test_set_remind_before_negative_and_missing():
    t = add_task(1, "t")
    assert set_remind_before(t, -1) is False
    assert set_remind_before(999999, 10) is False


# --- get_due_tasks учитывает remind_before ---

def test_due_with_remind_before_triggers_early():
    t = add_task(1, "meeting", "2026-05-17 12:00:00")
    set_remind_before(t, 30)  # сработать в 11:30
    assert [x["id"] for x in get_due_tasks("2026-05-17 11:30:00")] == [t]
    assert get_due_tasks("2026-05-17 11:29:00") == []


def test_due_without_remind_before_unchanged():
    t = add_task(1, "plain", "2026-05-17 12:00:00")
    assert get_due_tasks("2026-05-17 11:59:00") == []
    assert [x["id"] for x in get_due_tasks("2026-05-17 12:00:00")] == [t]


# --- /search ---

async def test_search_usage():
    u = make_update()
    await bot.search_command(u, make_context([]))
    assert "Использование" in reply(u)


async def test_search_found_and_not_found():
    u = make_update()
    tasks = [{"id": 1, "description": "Купить хлеб", "due_date": None}]
    with patch.object(bot, "search_tasks", return_value=tasks):
        await bot.search_command(u, make_context(["хлеб"]))
    assert "Найдено" in reply(u) and "Купить хлеб" in reply(u)

    u = make_update()
    with patch.object(bot, "search_tasks", return_value=[]):
        await bot.search_command(u, make_context(["zzz"]))
    assert "ничего не найдено" in reply(u).lower()


# --- /remindbefore ---

async def test_remindbefore_validation():
    u = make_update()
    await bot.remindbefore_command(u, make_context(["7"]))
    assert "Использование" in reply(u)

    u = make_update()
    await bot.remindbefore_command(u, make_context(["abc", "10"]))
    assert "числом" in reply(u).lower()

    u = make_update()
    await bot.remindbefore_command(u, make_context(["7", "xx"]))
    assert "off" in reply(u).lower()

    u = make_update()
    await bot.remindbefore_command(u, make_context(["7", "-5"]))
    assert "< 0" in reply(u)


async def test_remindbefore_set_clear_notfound():
    u = make_update()
    with patch.object(bot, "set_remind_before", return_value=True) as m:
        await bot.remindbefore_command(u, make_context(["7", "15"]))
    m.assert_called_once_with(7, 15)
    assert "за 15 мин" in reply(u)

    u = make_update()
    with patch.object(bot, "set_remind_before", return_value=True) as m:
        await bot.remindbefore_command(u, make_context(["7", "off"]))
    m.assert_called_once_with(7, None)
    assert "ровно в срок" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "set_remind_before", return_value=False):
        await bot.remindbefore_command(u, make_context(["7", "15"]))
    assert "не найдена" in reply(u).lower()

"""Тесты хендлеров бота с замоканным Telegram (без сети)."""
from unittest.mock import AsyncMock, MagicMock, patch

import bot


def make_update(text="/add x", user_id=42):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.mention_html.return_value = "<a>User</a>"
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.message.reply_html = AsyncMock()
    return update


def make_context(args=None):
    ctx = MagicMock()
    ctx.args = [] if args is None else args
    return ctx


def reply(update):
    return update.message.reply_text.call_args.args[0]


async def test_start_greets():
    update = make_update()
    await bot.start(update, make_context())
    update.message.reply_html.assert_awaited_once()


async def test_help_lists_commands():
    update = make_update()
    await bot.help_command(update, make_context())
    assert "/add" in reply(update)


async def test_add_with_due_date():
    update = make_update("/add Отчёт 2026-05-18 15:00")
    with patch.object(bot, "add_task", return_value=7) as add:
        await bot.add_task_command(update, make_context())
    add.assert_called_once_with(42, "Отчёт", "2026-05-18 15:00:00")
    assert "2026-05-18 15:00:00" in reply(update)


async def test_add_without_due_date():
    update = make_update("/add Купить молоко")
    with patch.object(bot, "add_task", return_value=1) as add:
        await bot.add_task_command(update, make_context())
    add.assert_called_once_with(42, "Купить молоко", None)


async def test_add_empty_description_rejected():
    update = make_update("/add")
    with patch.object(bot, "add_task") as add:
        await bot.add_task_command(update, make_context())
    add.assert_not_called()
    assert "описание" in reply(update).lower()


async def test_add_db_error_handled():
    update = make_update("/add Задача")
    with patch.object(bot, "add_task", side_effect=RuntimeError("db down")):
        await bot.add_task_command(update, make_context())
    assert "ошибка" in reply(update).lower()


async def test_list_empty():
    update = make_update()
    with patch.object(bot, "get_tasks", return_value=[]):
        await bot.list_tasks(update, make_context())
    assert "нет активных" in reply(update).lower()


async def test_list_with_tasks():
    update = make_update()
    tasks = [
        {"id": 1, "description": "A", "due_date": None},
        {"id": 2, "description": "B", "due_date": "2026-05-18 15:00:00"},
    ]
    with patch.object(bot, "get_tasks", return_value=tasks):
        await bot.list_tasks(update, make_context())
    out = reply(update)
    assert "A" in out and "B" in out and "2026-05-18 15:00:00" in out


async def test_done_requires_arg():
    update = make_update()
    await bot.done_task(update, make_context(args=[]))
    assert "номер задачи" in reply(update).lower()


async def test_done_rejects_non_int():
    update = make_update()
    await bot.done_task(update, make_context(args=["abc"]))
    assert "числом" in reply(update).lower()


async def test_done_success():
    update = make_update()
    with patch.object(bot, "mark_task_done", return_value=True) as m:
        await bot.done_task(update, make_context(args=["5"]))
    m.assert_called_once_with(5)
    assert "выполненная" in reply(update).lower()


async def test_done_not_found():
    update = make_update()
    with patch.object(bot, "mark_task_done", return_value=False):
        await bot.done_task(update, make_context(args=["999"]))
    assert "не найдена" in reply(update).lower()

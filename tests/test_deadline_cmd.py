"""Фаза 7.3: команды /deadline и /remind (новая модель)."""
from unittest.mock import AsyncMock, MagicMock, patch

import bot


def make_update(user_id=42):
    u = MagicMock()
    u.effective_user.id = user_id
    u.message.reply_text = AsyncMock()
    return u


def make_context(args):
    c = MagicMock()
    c.args = args
    return c


def reply(u):
    return u.message.reply_text.call_args.args[0]


# --- /deadline ---

async def test_deadline_usage():
    u = make_update()
    await bot.deadline_command(u, make_context(["7"]))
    assert "Использование" in reply(u) and "/deadline" in reply(u)


async def test_deadline_non_int():
    u = make_update()
    await bot.deadline_command(u, make_context(["abc", "2026-05-18", "15:00"]))
    assert "числом" in reply(u).lower()


async def test_deadline_bad_date():
    u = make_update()
    await bot.deadline_command(u, make_context(["7", "когда-нибудь"]))
    assert "дату" in reply(u).lower()


async def test_deadline_success_utc():
    u = make_update()
    with patch.object(bot, "set_deadline", return_value=True) as m:
        await bot.deadline_command(u, make_context(["7", "2026-05-18", "15:00"]))
    m.assert_called_once_with(7, "2026-05-18 15:00:00")
    assert "Срок №7" in reply(u)


async def test_deadline_off_clears():
    u = make_update()
    with patch.object(bot, "set_deadline", return_value=True) as m:
        await bot.deadline_command(u, make_context(["7", "off"]))
    m.assert_called_once_with(7, None)
    assert "снят" in reply(u).lower()


async def test_deadline_not_found():
    u = make_update()
    with patch.object(bot, "set_deadline", return_value=False):
        await bot.deadline_command(u, make_context(["7", "2026-05-18", "15:00"]))
    assert "не найдена" in reply(u).lower()


# --- /remind ---

async def test_remind_success_utc():
    u = make_update()
    with patch.object(bot, "set_reminder_at", return_value=True) as m:
        await bot.remind_command(u, make_context(["3", "18.05.2026", "09:30"]))
    m.assert_called_once_with(3, "2026-05-18 09:30:00")
    assert "Напоминание №3" in reply(u)


async def test_remind_off_and_not_found():
    u = make_update()
    with patch.object(bot, "set_reminder_at", return_value=True) as m:
        await bot.remind_command(u, make_context(["3", "off"]))
    m.assert_called_once_with(3, None)
    assert "снят" in reply(u).lower()

    u = make_update()
    with patch.object(bot, "set_reminder_at", return_value=False):
        await bot.remind_command(u, make_context(["3", "off"]))
    assert "не найдена" in reply(u).lower()


async def test_remind_usage_and_non_int():
    u = make_update()
    await bot.remind_command(u, make_context([]))
    assert "Использование" in reply(u) and "/remind" in reply(u)

    u = make_update()
    await bot.remind_command(u, make_context(["x", "2026-05-18", "09:30"]))
    assert "числом" in reply(u).lower()

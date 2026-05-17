"""Фаза 5.8: тесты часовых поясов."""
from unittest.mock import AsyncMock, MagicMock

import pytest

import bot
from database import add_task, get_tasks, get_timezone, set_timezone
from tzutil import to_local, to_utc, valid_timezone


def make_update(user_id=42, text=None):
    update = MagicMock()
    update.effective_user.id = user_id
    if text is not None:
        update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def make_context(args):
    ctx = MagicMock()
    ctx.args = args
    return ctx


def reply(update):
    return update.message.reply_text.call_args.args[0]


# --- tzutil ---

@pytest.mark.parametrize(
    "tz, ok",
    [("UTC", True), ("Europe/Moscow", True), ("Bad/Zone", False), ("", False)],
)
def test_valid_timezone(tz, ok):
    assert valid_timezone(tz) is ok


def test_utc_identity():
    assert to_utc("2026-05-17 12:00:00", "UTC") == "2026-05-17 12:00:00"
    assert to_local("2026-05-17 12:00:00", "UTC") == "2026-05-17 12:00:00"


def test_to_utc_and_back_moscow():
    # Москва = UTC+3 (без перехода на летнее время)
    assert to_utc("2026-05-17 12:00:00", "Europe/Moscow") == "2026-05-17 09:00:00"
    assert to_local("2026-05-17 09:00:00", "Europe/Moscow") == "2026-05-17 12:00:00"


def test_to_utc_new_york_dst():
    # Нью-Йорк в мае = летнее время, UTC-4
    assert to_utc("2026-05-17 12:00:00", "America/New_York") == "2026-05-17 16:00:00"


# --- get/set_timezone ---

def test_timezone_default_is_utc():
    assert get_timezone(1) == "UTC"


def test_set_timezone_valid_and_overwrite():
    assert set_timezone(1, "Europe/Moscow") is True
    assert get_timezone(1) == "Europe/Moscow"
    assert set_timezone(1, "Asia/Tokyo") is True
    assert get_timezone(1) == "Asia/Tokyo"


def test_set_timezone_invalid_rejected():
    set_timezone(1, "Europe/Moscow")
    assert set_timezone(1, "Nope/Nope") is False
    assert get_timezone(1) == "Europe/Moscow"  # не изменился


# --- /timezone ---

async def test_timezone_show_default():
    u = make_update(user_id=777)
    await bot.timezone_command(u, make_context([]))
    assert "UTC" in reply(u)


async def test_timezone_set_valid():
    u = make_update(user_id=778)
    await bot.timezone_command(u, make_context(["Europe/Moscow"]))
    assert "Europe/Moscow" in reply(u)
    assert get_timezone(778) == "Europe/Moscow"


async def test_timezone_set_invalid():
    u = make_update(user_id=779)
    await bot.timezone_command(u, make_context(["Bad/Zone"]))
    assert "не распознан" in reply(u).lower()
    assert get_timezone(779) == "UTC"


# --- интеграция: /add хранит UTC, /list показывает локально ---

async def test_add_stores_utc_for_non_utc_user():
    set_timezone(555, "Europe/Moscow")
    u = make_update(user_id=555, text="/add Митинг 2026-05-17 12:00")
    await bot.add_task_command(u, make_context([]))
    # хранится в UTC (12:00 МСК -> 09:00 UTC)
    assert get_tasks(555)[0]["due_date"] == "2026-05-17 09:00:00"
    # пользователю показано его локальное время
    assert "2026-05-17 12:00:00" in reply(u)


async def test_list_shows_local_time():
    set_timezone(556, "Europe/Moscow")
    add_task(556, "Звонок", "2026-05-17 09:00:00")  # UTC в БД
    u = make_update(user_id=556)
    await bot.list_tasks(u, make_context([]))
    assert "2026-05-17 12:00:00" in reply(u)  # показано в МСК


async def test_default_user_unaffected():
    # без установленного пояса всё как раньше (UTC-identity)
    u = make_update(user_id=999, text="/add Тест 2026-05-18 15:00")
    await bot.add_task_command(u, make_context([]))
    assert get_tasks(999)[0]["due_date"] == "2026-05-18 15:00:00"

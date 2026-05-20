"""Фаза 5.8: тесты часовых поясов (БД + tzutil).

С Phase 11.1 чат-команды убраны — интеграционные UTC↔локаль
сценарии живут в `test_webapp.py` через Mini App API.
"""
import pytest

from database import get_timezone, set_timezone
from tzutil import to_local, to_utc, valid_timezone

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



"""Утилиты часовых поясов (stdlib zoneinfo, Python 3.11)."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_FMT = "%Y-%m-%d %H:%M:%S"


def valid_timezone(tz: str) -> bool:
    """True, если `tz` — корректная IANA-зона."""
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def to_utc(local: str, tz: str) -> str:
    """Локальное время `local` (в зоне `tz`) → наивная UTC-строка."""
    dt = datetime.strptime(local, _FMT).replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(ZoneInfo("UTC")).strftime(_FMT)


def to_local(utc: str, tz: str) -> str:
    """Наивная UTC-строка → локальное время в зоне `tz`."""
    dt = datetime.strptime(utc, _FMT).replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo(tz)).strftime(_FMT)

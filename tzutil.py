"""Утилиты часовых поясов (stdlib zoneinfo, Python 3.11)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_FMT = "%Y-%m-%d %H:%M:%S"
_ZERO = timedelta(0)


def valid_timezone(tz: str) -> bool:
    """True, если `tz` – корректная IANA-зона."""
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


# --- Курируемый список общих часовых поясов (Фаза 10.5) ---
#
# Пользователю нужен короткий список «человеческих» вариантов вместо
# свободного ввода IANA-имени (`Europe/Moscow` помнят не все). Сгруппирован
# по регионам/смещениям. Названия – на русском, IANA-id – машинный value.
# Полные 600+ зон не выводим: 95% пользователей нужны крупные города
# своего региона. Если нужного нет – пусть открывают часовой пояс через
# чат-бота (`/timezone <IANA>`) либо мы добавим по запросу.

_COMMON_TIMEZONES: list[dict] = [
    # Россия – от запада к востоку, по смещению.
    {"tz": "Europe/Kaliningrad",      "label": "Калининград",      "group": "Россия"},
    {"tz": "Europe/Moscow",           "label": "Москва",           "group": "Россия"},
    {"tz": "Europe/Samara",           "label": "Самара",           "group": "Россия"},
    {"tz": "Asia/Yekaterinburg",      "label": "Екатеринбург",     "group": "Россия"},
    {"tz": "Asia/Omsk",               "label": "Омск",             "group": "Россия"},
    {"tz": "Asia/Novosibirsk",        "label": "Новосибирск",      "group": "Россия"},
    {"tz": "Asia/Krasnoyarsk",        "label": "Красноярск",       "group": "Россия"},
    {"tz": "Asia/Irkutsk",            "label": "Иркутск",          "group": "Россия"},
    {"tz": "Asia/Yakutsk",            "label": "Якутск",           "group": "Россия"},
    {"tz": "Asia/Vladivostok",        "label": "Владивосток",      "group": "Россия"},
    {"tz": "Asia/Magadan",            "label": "Магадан",          "group": "Россия"},
    {"tz": "Asia/Kamchatka",          "label": "Камчатка",         "group": "Россия"},
    # СНГ / соседи.
    {"tz": "Europe/Minsk",            "label": "Минск",            "group": "СНГ"},
    {"tz": "Europe/Kyiv",             "label": "Киев",             "group": "СНГ"},
    {"tz": "Asia/Tbilisi",            "label": "Тбилиси",          "group": "СНГ"},
    {"tz": "Asia/Yerevan",            "label": "Ереван",           "group": "СНГ"},
    {"tz": "Asia/Baku",               "label": "Баку",             "group": "СНГ"},
    {"tz": "Asia/Almaty",             "label": "Алматы",           "group": "СНГ"},
    {"tz": "Asia/Tashkent",           "label": "Ташкент",          "group": "СНГ"},
    {"tz": "Asia/Bishkek",            "label": "Бишкек",           "group": "СНГ"},
    {"tz": "Asia/Dushanbe",           "label": "Душанбе",          "group": "СНГ"},
    {"tz": "Asia/Ashgabat",           "label": "Ашхабад",          "group": "СНГ"},
    # Европа.
    {"tz": "Europe/London",           "label": "Лондон",           "group": "Европа"},
    {"tz": "Europe/Paris",            "label": "Париж",            "group": "Европа"},
    {"tz": "Europe/Berlin",           "label": "Берлин",           "group": "Европа"},
    {"tz": "Europe/Amsterdam",        "label": "Амстердам",        "group": "Европа"},
    {"tz": "Europe/Madrid",           "label": "Мадрид",           "group": "Европа"},
    {"tz": "Europe/Rome",             "label": "Рим",              "group": "Европа"},
    {"tz": "Europe/Warsaw",           "label": "Варшава",          "group": "Европа"},
    {"tz": "Europe/Stockholm",        "label": "Стокгольм",        "group": "Европа"},
    {"tz": "Europe/Helsinki",         "label": "Хельсинки",        "group": "Европа"},
    {"tz": "Europe/Athens",           "label": "Афины",            "group": "Европа"},
    {"tz": "Europe/Istanbul",         "label": "Стамбул",          "group": "Европа"},
    # Азия.
    {"tz": "Asia/Dubai",              "label": "Дубай",            "group": "Азия"},
    {"tz": "Asia/Tehran",             "label": "Тегеран",          "group": "Азия"},
    {"tz": "Asia/Karachi",            "label": "Карачи",           "group": "Азия"},
    {"tz": "Asia/Kolkata",            "label": "Калькутта",        "group": "Азия"},
    {"tz": "Asia/Bangkok",            "label": "Бангкок",          "group": "Азия"},
    {"tz": "Asia/Shanghai",           "label": "Шанхай",           "group": "Азия"},
    {"tz": "Asia/Hong_Kong",          "label": "Гонконг",          "group": "Азия"},
    {"tz": "Asia/Singapore",          "label": "Сингапур",         "group": "Азия"},
    {"tz": "Asia/Seoul",              "label": "Сеул",             "group": "Азия"},
    {"tz": "Asia/Tokyo",              "label": "Токио",            "group": "Азия"},
    # Америка.
    {"tz": "America/New_York",        "label": "Нью-Йорк",         "group": "Америка"},
    {"tz": "America/Chicago",         "label": "Чикаго",           "group": "Америка"},
    {"tz": "America/Denver",          "label": "Денвер",           "group": "Америка"},
    {"tz": "America/Los_Angeles",     "label": "Лос-Анджелес",     "group": "Америка"},
    {"tz": "America/Anchorage",       "label": "Анкоридж",         "group": "Америка"},
    {"tz": "Pacific/Honolulu",        "label": "Гонолулу",         "group": "Америка"},
    {"tz": "America/Toronto",         "label": "Торонто",          "group": "Америка"},
    {"tz": "America/Mexico_City",     "label": "Мехико",           "group": "Америка"},
    {"tz": "America/Sao_Paulo",       "label": "Сан-Паулу",        "group": "Америка"},
    {"tz": "America/Argentina/Buenos_Aires", "label": "Буэнос-Айрес", "group": "Америка"},
    # Океания.
    {"tz": "Australia/Sydney",        "label": "Сидней",           "group": "Океания"},
    {"tz": "Australia/Melbourne",     "label": "Мельбурн",         "group": "Океания"},
    {"tz": "Australia/Perth",         "label": "Перт",             "group": "Океания"},
    {"tz": "Pacific/Auckland",        "label": "Окленд",           "group": "Океания"},
    # Африка.
    {"tz": "Africa/Cairo",            "label": "Каир",             "group": "Африка"},
    {"tz": "Africa/Johannesburg",     "label": "Йоханнесбург",     "group": "Африка"},
    {"tz": "Africa/Lagos",            "label": "Лагос",            "group": "Африка"},
    # Универсальная.
    {"tz": "UTC",                     "label": "UTC",              "group": "Прочее"},
]


def _format_offset(tz: str, now: datetime | None = None) -> str:
    """Текущее смещение `tz` от UTC в формате `UTC+03:00` / `UTC-05:00`."""
    ref = now or datetime.now(ZoneInfo("UTC"))
    # После `astimezone` datetime aware → utcoffset() возвращает timedelta
    # (а не None – None бывает только у наивных datetime).
    offset = ref.astimezone(ZoneInfo(tz)).utcoffset() or _ZERO
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def list_common_timezones() -> list[dict]:
    """
    Возвращает курируемый список с актуальными смещениями. Каждая
    запись: `{tz, label, group, offset, offset_minutes}`. Сортировка –
    по `offset_minutes` (с запада на восток), затем по label, чтобы UI
    отображал зоны в естественном порядке.
    """
    now = datetime.now(ZoneInfo("UTC"))
    out = []
    for item in _COMMON_TIMEZONES:
        tz = item["tz"]
        offset = ZoneInfo(tz).utcoffset(now)
        mins = int(offset.total_seconds() // 60) if offset else 0
        out.append({
            "tz": tz,
            "label": item["label"],
            "group": item["group"],
            "offset": _format_offset(tz, now),
            "offset_minutes": mins,
        })
    out.sort(key=lambda d: (d["offset_minutes"], d["label"]))
    return out

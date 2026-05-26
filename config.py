"""
Конфигурация бота.

Секреты читаются из переменных окружения / `.env` и НЕ хранятся в коде.
Скопируйте `.env.example` в `.env` и заполните значения.
"""
import os

# python-dotenv опционален: если установлен – подхватываем .env автоматически.
# Если нет – значения берутся из реального окружения процесса.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Токен бота. Пустая строка по умолчанию – проверка наличия делается при
# запуске бота (bot.py), чтобы тесты/БД могли импортироваться без токена.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Путь к локальной SQLite-базе.
DATABASE_PATH = os.environ.get("DATABASE_PATH", "./data/tasks.db")

# Часовой пояс бота.
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Moscow")

# Интервал проверки напоминаний планировщиком, секунды.
SCHEDULER_CHECK_INTERVAL = int(os.environ.get("SCHEDULER_CHECK_INTERVAL", "60"))

# URL Mini App для кнопки в /start (Phase 11.1: команды убрали, остался
# только запуск Mini App). Должен быть HTTPS, иначе Telegram не покажет
# WebApp-кнопку.
# Phase 11.26: дефолт обновлён на app.reminderr.ru. Раньше домен
# reminderr.ru указывал на Mini App; теперь это отдельный сайт
# (Pterodactyl), а Mini App переехал на поддомен app.reminderr.ru.
# Если на проде `.env` не задавал MINI_APP_URL, бот при каждом старте
# через `set_chat_menu_button` ставил глобальную кнопку «Открыть» на
# старый домен → пользователь иногда попадал на чужой сайт.
MINI_APP_URL = os.environ.get("MINI_APP_URL", "https://app.reminderr.ru/")


def _parse_allowlist(raw: str) -> set:
    """Парсит CSV-список ID/имён в set из непустых элементов."""
    return {x.strip().lstrip("@") for x in (raw or "").split(",") if x.strip()}


# Phase 11.3: ограничение доступа одним пользователем.
# Указывать numeric Telegram ID (стабильнее) – но username тоже принимаем,
# т.к. ID не каждый знает наизусть. ID можно подсмотреть, написав боту
# @userinfobot, или в логах webapp при первом обращении.
# Пустой allowlist = доступ открыт всем (как было до Phase 11.3).
ALLOWED_USER_IDS = {
    int(x) for x in _parse_allowlist(os.environ.get("ALLOWED_USER_IDS", ""))
    if x.isdigit()
}
ALLOWED_USERNAMES = _parse_allowlist(os.environ.get("ALLOWED_USERNAMES", ""))


def is_user_allowed(user_id: int | None, username: str | None) -> bool:
    """
    True, если пользователь имеет право пользоваться ботом.
    - Если оба allowlist'а пусты → доступ всем (старое поведение).
    - Иначе пускаем, если id ∈ ALLOWED_USER_IDS или username ∈ ALLOWED_USERNAMES.
    """
    if not ALLOWED_USER_IDS and not ALLOWED_USERNAMES:
        return True
    if user_id is not None and user_id in ALLOWED_USER_IDS:
        return True
    if username and username.lstrip("@") in ALLOWED_USERNAMES:
        return True
    return False

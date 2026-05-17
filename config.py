"""
Конфигурация бота.

Секреты читаются из переменных окружения / `.env` и НЕ хранятся в коде.
Скопируйте `.env.example` в `.env` и заполните значения.
"""
import os

# python-dotenv опционален: если установлен — подхватываем .env автоматически.
# Если нет — значения берутся из реального окружения процесса.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Токен бота. Пустая строка по умолчанию — проверка наличия делается при
# запуске бота (bot.py), чтобы тесты/БД могли импортироваться без токена.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Путь к локальной SQLite-базе.
DATABASE_PATH = os.environ.get("DATABASE_PATH", "./data/tasks.db")

# Часовой пояс бота.
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Moscow")

# Интервал проверки напоминаний планировщиком, секунды.
SCHEDULER_CHECK_INTERVAL = int(os.environ.get("SCHEDULER_CHECK_INTERVAL", "60"))

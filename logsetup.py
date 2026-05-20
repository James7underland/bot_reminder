"""
Унифицированная настройка логов (Фаза 10.3).

Цели:
- Один формат во всех процессах (`bot.py`, `webapp.py`).
- StreamHandler в stdout — попадает в systemd journal автоматически.
- RotatingFileHandler (опционально) — файл `<LOG_DIR>/<name>.log`
  с ротацией 5×10 МБ, чтобы /var/log не разрастался на VPS.
- Глушение шумных сторонних логгеров (`httpx` пишет URL запроса к
  Telegram API с токеном бота — обязательно к WARNING).

`LOG_DIR` берётся из env. Если не задан или путь недоступен — файловое
логирование молча отключается (только stdout), чтобы не падать при
локальной разработке без прав на /var/log.
"""
import logging
import logging.handlers
import os
from pathlib import Path

_FMT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# httpx/httpcore логируют URL запроса к Telegram API, в котором лежит
# токен бота. apscheduler/telegram-py-bot слишком многословны на INFO.
_NOISY_LOGGERS = ("httpx", "httpcore", "apscheduler", "telegram")


def setup_logging(name: str, level: int = logging.INFO) -> None:
    """
    Конфигурирует root-логгер для процесса `name` (например `"bot"`
    или `"webapp"`). Идемпотентно — повторный вызов не дублирует
    хендлеры. Возвращает None; модули как обычно тянут именованные
    логгеры через `logging.getLogger(__name__)`.
    """
    root = logging.getLogger()
    # Идемпотентность: если уже сконфигурировано нашим маркером —
    # перенастраивать не нужно (например, gunicorn перезаражает модуль).
    if getattr(root, "_bot_reminder_configured", False):
        return
    root.setLevel(level)

    formatter = logging.Formatter(_FMT)

    # stdout (попадает в journalctl при запуске под systemd).
    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    root.addHandler(sh)

    # Файл с ротацией — только если LOG_DIR задан и доступен на запись.
    log_dir = os.environ.get("LOG_DIR")
    if log_dir:
        try:
            path = Path(log_dir)
            path.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                path / f"{name}.log",
                maxBytes=10 * 1024 * 1024,  # 10 МБ на файл
                backupCount=5,              # 5 архивных копий → ~60 МБ
                encoding="utf-8",
            )
            fh.setFormatter(formatter)
            root.addHandler(fh)
        except OSError as e:   # нет прав / диск/путь невалидный
            root.warning("logsetup: file logging disabled (%s)", e)

    for lname in _NOISY_LOGGERS:
        logging.getLogger(lname).setLevel(logging.WARNING)

    root._bot_reminder_configured = True

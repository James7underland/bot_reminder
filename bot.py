"""
Главный модуль Telegram-бота-напоминалки.
"""
import logging
import re
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import TELEGRAM_BOT_TOKEN
from database import (
    add_task,
    get_tasks,
    init_db,
    mark_task_done,
    mark_task_undone,
    set_reminder,
    update_task_description,
)
from scheduler import setup_scheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Поддерживаются ТОЛЬКО явные форматы даты-времени (решение №4 — без
# естественного языка). (strptime-формат, regex) — порядок важен.
_DATE_FORMATS = (
    ("%Y-%m-%d %H:%M", r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}"),
    ("%d.%m.%Y %H:%M", r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}"),
)
_COMMAND_RE = re.compile(r"^/add(?:@\w+)?\s*", re.IGNORECASE)


def _match_due(body: str) -> tuple[re.Match, str] | None:
    """Ищет первый валидный токен даты-времени. (match, нормализованная)."""
    for fmt, pattern in _DATE_FORMATS:
        match = re.search(pattern, body)
        if not match:
            continue
        try:
            dt = datetime.strptime(match.group(), fmt)
        except ValueError:
            continue
        return match, dt.strftime("%Y-%m-%d %H:%M:%S")
    return None


def parse_add_command(text: str) -> tuple[str, str | None]:
    """
    Разбирает текст команды /add.

    Поддерживаются только форматы `YYYY-MM-DD HH:MM` и `DD.MM.YYYY HH:MM`.
    Дата-подобный, но невалидный токен (напр. `2026-13-40 99:99`) датой не
    считается и остаётся частью описания.

    Returns:
        (описание, due_date|None), где due_date нормализован к
        `YYYY-MM-DD HH:MM:SS`.
    """
    body = _COMMAND_RE.sub("", text or "", count=1).strip()
    found = _match_due(body)
    if found is None:
        return body, None
    match, due_date = found
    description = (body[: match.start()] + body[match.end():]).strip()
    description = re.sub(r"\s{2,}", " ", description)
    return description, due_date


def parse_datetime(text: str) -> str | None:
    """Парсит строку даты-времени в `YYYY-MM-DD HH:MM:SS` или None."""
    found = _match_due((text or "").strip())
    return found[1] if found else None

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Привет {user.mention_html()}! Я бот-напоминалка, как Microsoft To Do."
        "\nИспользуй /help, чтобы узнать, что я умею."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение со списком команд."""
    help_text = (
        "/start - Начать работу с ботом\n"
        "/help - Показать это сообщение\n"
        "/add <описание> [YYYY-MM-DD HH:MM] - Добавить задачу\n"
        "/list - Показать все активные задачи\n"
        "/done <номер> - Отметить задачу как выполненную\n"
        "/undone <номер> - Вернуть задачу в активные\n"
        "/edit <номер> <описание> - Изменить описание\n"
        "/reschedule <номер> <YYYY-MM-DD HH:MM> - Перенести напоминание"
    )
    await update.message.reply_text(help_text)


async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /add для добавления новой задачи."""
    user_id = update.effective_user.id
    text = update.message.text

    description, due_date = parse_add_command(text)

    # Проверяем, что описание не пустое
    if not description:
        await update.message.reply_text("Пожалуйста, укажите описание задачи.")
        return

    try:
        task_id = add_task(user_id, description, due_date)
        if due_date:
            msg = f'Задача "{description}" добавлена! Напоминание: {due_date}.'
        else:
            msg = f'Задача "{description}" добавлена! Без напоминания.'
        await update.message.reply_text(msg)
        logger.info("user=%s added task=%s due=%s", user_id, task_id, due_date)
    except Exception as e:
        logger.error("add_task failed for user=%s: %s", user_id, e)
        await update.message.reply_text("Произошла ошибка при добавлении задачи.")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет пользователю список его активных задач."""
    user_id = update.effective_user.id
    tasks = get_tasks(user_id)

    if not tasks:
        await update.message.reply_text("У вас пока нет активных задач.")
        return

    # Форматируем список задач
    task_list = "Ваши активные задачи:\n"
    for task in tasks:
        due_str = f", напоминание: {task['due_date']}" if task['due_date'] else ""
        task_list += f"• {task['id']}. {task['description']}{due_str}\n"

    await update.message.reply_text(task_list)


async def done_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отмечает задачу как выполненную."""
    # Ожидаем, что после команды /done будет номер задачи
    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите номер задачи. Пример: /done 1")
        return

    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Номер задачи должен быть числом.")
        return

    success = mark_task_done(task_id)
    if success:
        await update.message.reply_text(f"Задача №{task_id} отмечена как выполненная!")
        logger.info("user=%s marked task=%s done", update.effective_user.id, task_id)
    else:
        await update.message.reply_text(f"Задача №{task_id} не найдена или уже выполнена.")


async def edit_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Изменяет описание задачи: /edit <id> <новое описание>."""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /edit <id> <новое описание>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Номер задачи должен быть числом.")
        return
    description = " ".join(context.args[1:]).strip()
    if not description:
        await update.message.reply_text("Пожалуйста, укажите новое описание.")
        return
    if update_task_description(task_id, description):
        await update.message.reply_text(f"Задача №{task_id} обновлена.")
    else:
        await update.message.reply_text(f"Задача №{task_id} не найдена.")


async def reschedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Переносит напоминание: /reschedule <id> <YYYY-MM-DD HH:MM>."""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /reschedule <id> <YYYY-MM-DD HH:MM>"
        )
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Номер задачи должен быть числом.")
        return
    due = parse_datetime(" ".join(context.args[1:]))
    if due is None:
        await update.message.reply_text(
            "Не понял дату. Форматы: YYYY-MM-DD HH:MM или DD.MM.YYYY HH:MM."
        )
        return
    if set_reminder(task_id, due):
        await update.message.reply_text(f"Напоминание №{task_id} перенесено на {due}.")
    else:
        await update.message.reply_text(f"Задача №{task_id} не найдена.")


async def undone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Возвращает выполненную задачу в активные: /undone <id>."""
    if not context.args:
        await update.message.reply_text("Использование: /undone <id>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Номер задачи должен быть числом.")
        return
    if mark_task_undone(task_id):
        await update.message.reply_text(f"Задача №{task_id} снова активна.")
    else:
        await update.message.reply_text(f"Задача №{task_id} не найдена.")


def main() -> None:  # pragma: no cover
    """Запускает бота (сетевой polling — вне unit-тестов)."""
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN не задан. Скопируйте .env.example в .env "
            "и укажите НОВЫЙ токен от @BotFather."
        )
    # Создаем приложение и передаем ему токен бота
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Инициализируем базу данных
    init_db()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_task_command))
    application.add_handler(CommandHandler("list", list_tasks))
    application.add_handler(CommandHandler("done", done_task))
    application.add_handler(CommandHandler("undone", undone_command))
    application.add_handler(CommandHandler("edit", edit_task_command))
    application.add_handler(CommandHandler("reschedule", reschedule_command))

    # Планировщик напоминаний (APScheduler)
    setup_scheduler(application)

    # Запускаем бота и пропускаем все обновления, которые пришли, когда он был выключен
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':  # pragma: no cover
    main()

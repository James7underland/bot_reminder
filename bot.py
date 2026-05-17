"""
Главный модуль Telegram-бота-напоминалки.
"""
import logging
import re
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import TELEGRAM_BOT_TOKEN
from database import add_task, get_tasks, init_db, mark_task_done
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

    for fmt, pattern in _DATE_FORMATS:
        match = re.search(pattern, body)
        if not match:
            continue
        try:
            dt = datetime.strptime(match.group(), fmt)
        except ValueError:
            continue
        due_date = dt.strftime("%Y-%m-%d %H:%M:%S")
        description = (body[: match.start()] + body[match.end():]).strip()
        description = re.sub(r"\s{2,}", " ", description)
        return description, due_date

    return body, None

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
        "/done <номер> - Отметить задачу как выполненную"
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

    # Планировщик напоминаний (APScheduler)
    setup_scheduler(application)

    # Запускаем бота и пропускаем все обновления, которые пришли, когда он был выключен
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':  # pragma: no cover
    main()

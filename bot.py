"""
Главный модуль Telegram-бота-напоминалки.
"""
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import logging
import re
from typing import Tuple, Optional

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Импортируем функции из других модулей
from config import TELEGRAM_BOT_TOKEN
from database import add_task, get_tasks, mark_task_done, init_db

# Функция для разбора команды /add
# Регулярное выражение для поиска даты в форматах: YYYY-MM-DD HH:MM, DD.MM.YYYY, HH:MM и т.д.
DATE_PATTERN = r'(\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?|\d{2}\.\d{2}\.\d{4}( \d{2}:\d{2})?|\d{2}:\d{2})'

def parse_add_command(text: str) -> Tuple[str, Optional[str]]:
    """
    Разбирает текст команды /add и извлекает описание и дату напоминания.

    Args:
        text: Полный текст команды (например, '/add Сделать отчет 2026-05-18 15:00').

    Returns:
        Кортеж (описание, дата_в_ISO_формате). Дата может быть None.
    """
    # Удаляем команду и пробел в начале
    text = text[len('/add'):].strip()
    
    # Ищем дату в тексте
    date_match = re.search(DATE_PATTERN, text)
    due_date = None
    description = text
    
    if date_match:
        # Извлекаем найденную дату
        raw_date = date_match.group()
        # Простая конвертация в ISO формат. В реальности нужно использовать библиотеку, например, dateutil.
        # Это заглушка для демонстрации.
        # Поддерживаем формат YYYY-MM-DD HH:MM
        if ' ' in raw_date: # Есть и дата, и время
            date_part, time_part = raw_date.split()
            if '.' in date_part: # DD.MM.YYYY
                day, month, year = date_part.split('.')
                iso_date = f"{year}-{month}-{day} {time_part}"
            else: # YYYY-MM-DD
                iso_date = f"{date_part} {time_part}"
        else: # Только дата или только время
            if '.' in raw_date: # DD.MM.YYYY
                day, month, year = raw_date.split('.')
                iso_date = f"{year}-{month}-{day} 00:00:00" # Время по умолчанию
            else: # Это может быть только время HH:MM
                iso_date = f"{raw_date}:00" # Добавляем секунды
                # В этом случае, возможно, нужно привязать к завтрашнему дню? Это уточнение требует логики.
                # Пока просто используем текущую дату.
                from datetime import datetime
                today = datetime.now().strftime("%Y-%m-%d")
                iso_date = f"{today} {iso_date}"
        due_date = iso_date
        # Удаляем найденную дату из описания
        description = text[:date_match.start()] + text[date_match.end():]
        description = description.strip()
        
    return description, due_date

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
        "/add <описание> [дата время] - Добавить задачу. Пример: /add Сделать отчет 2026-05-18 15:00\n"
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
            await update.message.reply_text(f"Задача \"{description}\" добавлена! Напоминание установлено на {due_date}.")
        else:
            await update.message.reply_text(f"Задача \"{description}\" добавлена! Напоминание не установлено.")
        logger.info(f"Пользователь {user_id} добавил задачу {task_id}: '{description}' (до {due_date})")
    except Exception as e:
        logger.error(f"Ошибка при добавлении задачи для пользователя {user_id}: {e}")
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
        logger.info(f"Пользователь {update.effective_user.id} отметил задачу {task_id} как выполненную.")
    else:
        await update.message.reply_text(f"Задача №{task_id} не найдена или уже выполнена.")


def main() -> None:
    """Запускает бота."""
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
    
    # Запускаем бота и пропускаем все обновления, которые пришли, когда он был выключен
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
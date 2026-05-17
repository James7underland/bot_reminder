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
    RECURRENCES,
    add_step,
    add_task,
    add_to_myday,
    assign_task_to_list,
    complete_task,
    create_list,
    delete_list,
    delete_step,
    get_lists,
    get_myday,
    get_steps,
    get_task,
    get_tasks,
    get_tasks_by_list,
    init_db,
    mark_step_done,
    mark_task_undone,
    remove_from_myday,
    rename_list,
    set_important,
    set_note,
    set_recurrence,
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
        "/reschedule <номер> <YYYY-MM-DD HH:MM> - Перенести напоминание\n"
        "/lists - Показать списки\n"
        "/newlist <имя> - Создать список\n"
        "/renamelist <id> <имя> - Переименовать список\n"
        "/dellist <id> - Удалить список (задачи останутся без списка)\n"
        "/movetask <task_id> <list_id|0> - Переместить задачу в список\n"
        "/repeat <номер> <daily|weekly|monthly|yearly|off> - Повтор задачи\n"
        "/important <id> - Пометить важной\n"
        "/unimportant <id> - Снять важность\n"
        "/list <important|due|alpha|created> - Список с сортировкой\n"
        "/addstep <task_id> <описание> - Добавить подзадачу\n"
        "/steps <task_id> - Заметка и подзадачи задачи\n"
        "/stepdone <step_id> | /stepundone <step_id> - Статус подзадачи\n"
        "/delstep <step_id> - Удалить подзадачу\n"
        "/note <task_id> [текст] - Показать/задать заметку\n"
        "/delnote <task_id> - Удалить заметку\n"
        "/myday [add|remove <id>] - «Мой день» (на сегодня)"
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
    arg = context.args[0] if context.args else None
    if arg in ("important", "due", "alpha", "created"):
        tasks = get_tasks(user_id, sort=arg)
        header = f"Задачи (сортировка: {arg}):\n"
    elif arg is not None:
        try:
            raw = int(arg)
        except ValueError:
            await update.message.reply_text(
                "Аргумент: ID списка (число, 0 — без списка) "
                "или сортировка important|due|alpha|created."
            )
            return
        list_id = None if raw == 0 else raw
        tasks = get_tasks_by_list(user_id, list_id)
        header = (
            "Задачи без списка:\n"
            if list_id is None
            else f"Задачи списка №{list_id}:\n"
        )
    else:
        tasks = get_tasks(user_id)
        header = "Ваши активные задачи:\n"

    if not tasks:
        await update.message.reply_text("У вас пока нет активных задач.")
        return

    # Форматируем список задач
    task_list = header
    for task in tasks:
        due_str = f", напоминание: {task['due_date']}" if task['due_date'] else ""
        rec = task.get("recurrence")
        rec_str = f" (повтор: {rec})" if rec else ""
        imp_str = "[важно] " if task.get("important") else ""
        task_list += (
            f"• {task['id']}. {imp_str}{task['description']}{due_str}{rec_str}\n"
        )

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

    result = complete_task(task_id)
    if result is None:
        await update.message.reply_text(
            f"Задача №{task_id} не найдена или уже выполнена."
        )
        return
    if result["recurred"]:
        await update.message.reply_text(
            f"Задача №{task_id} выполнена. "
            f"Следующее повторение: {result['next_due']}."
        )
    else:
        await update.message.reply_text(f"Задача №{task_id} выполнена!")
    logger.info("user=%s completed task=%s", update.effective_user.id, task_id)


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


async def lists_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает списки пользователя."""
    lists = get_lists(update.effective_user.id)
    if not lists:
        await update.message.reply_text(
            "У вас пока нет списков. Создать: /newlist <имя>"
        )
        return
    text = "Ваши списки:\n"
    for lst in lists:
        text += f"• {lst['id']}. {lst['name']}\n"
    await update.message.reply_text(text)


async def newlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создаёт список: /newlist <имя>."""
    name = " ".join(context.args).strip() if context.args else ""
    if not name:
        await update.message.reply_text("Использование: /newlist <имя>")
        return
    list_id = create_list(update.effective_user.id, name)
    await update.message.reply_text(f'Список "{name}" создан (№{list_id}).')


async def renamelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Переименовывает список: /renamelist <id> <имя>."""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /renamelist <id> <новое имя>")
        return
    try:
        list_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID списка должен быть числом.")
        return
    name = " ".join(context.args[1:]).strip()
    if not name:
        await update.message.reply_text("Укажите новое имя списка.")
        return
    if rename_list(list_id, name):
        await update.message.reply_text(f'Список №{list_id} переименован в "{name}".')
    else:
        await update.message.reply_text(f"Список №{list_id} не найден.")


async def dellist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаляет список (задачи остаются без списка): /dellist <id>."""
    if not context.args:
        await update.message.reply_text("Использование: /dellist <id>")
        return
    try:
        list_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID списка должен быть числом.")
        return
    if delete_list(list_id):
        await update.message.reply_text(
            f"Список №{list_id} удалён (задачи остались без списка)."
        )
    else:
        await update.message.reply_text(f"Список №{list_id} не найден.")


async def movetask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Перемещает задачу в список: /movetask <task_id> <list_id|0>."""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /movetask <task_id> <list_id|0>"
        )
        return
    try:
        task_id = int(context.args[0])
        raw_list = int(context.args[1])
    except ValueError:
        await update.message.reply_text("ID задачи и списка должны быть числами.")
        return
    user_id = update.effective_user.id
    target = None if raw_list == 0 else raw_list
    if target is not None and target not in {
        lst["id"] for lst in get_lists(user_id)
    }:
        await update.message.reply_text(f"Список №{target} не найден.")
        return
    if assign_task_to_list(task_id, target):
        where = "без списка" if target is None else f"в список №{target}"
        await update.message.reply_text(f"Задача №{task_id} перемещена {where}.")
    else:
        await update.message.reply_text(f"Задача №{task_id} не найдена.")


async def repeat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Задаёт повтор: /repeat <id> <daily|weekly|monthly|yearly|off>."""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Использование: /repeat <id> <daily|weekly|monthly|yearly|off>"
        )
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Номер задачи должен быть числом.")
        return
    value = context.args[1].lower()
    if value in ("off", "none", "нет"):
        recurrence: str | None = None
    elif value in RECURRENCES:
        recurrence = value
    else:
        await update.message.reply_text(
            "Допустимо: daily, weekly, monthly, yearly или off."
        )
        return
    if not set_recurrence(task_id, recurrence):
        await update.message.reply_text(f"Задача №{task_id} не найдена.")
        return
    if recurrence is None:
        await update.message.reply_text(f"Повтор для №{task_id} отключён.")
    else:
        await update.message.reply_text(
            f"Задача №{task_id} будет повторяться: {recurrence}."
        )


async def _set_important(
    update: Update, context: ContextTypes.DEFAULT_TYPE, value: bool
) -> None:
    if not context.args:
        cmd = "/important" if value else "/unimportant"
        await update.message.reply_text(f"Использование: {cmd} <id>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Номер задачи должен быть числом.")
        return
    if not set_important(task_id, value):
        await update.message.reply_text(f"Задача №{task_id} не найдена.")
        return
    if value:
        await update.message.reply_text(f"Задача №{task_id} помечена важной.")
    else:
        await update.message.reply_text(f"С задачи №{task_id} снята важность.")


async def important_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Помечает задачу важной: /important <id>."""
    await _set_important(update, context, True)


async def unimportant_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Снимает важность: /unimportant <id>."""
    await _set_important(update, context, False)


async def addstep_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавляет подзадачу: /addstep <task_id> <описание>."""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /addstep <task_id> <описание>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом.")
        return
    desc = " ".join(context.args[1:]).strip()
    if not desc:
        await update.message.reply_text("Опишите подзадачу.")
        return
    step_id = add_step(task_id, desc)
    if step_id is None:
        await update.message.reply_text(f"Задача №{task_id} не найдена.")
    else:
        await update.message.reply_text(
            f"Подзадача №{step_id} добавлена к задаче №{task_id}."
        )


async def steps_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает заметку и подзадачи задачи: /steps <task_id>."""
    if not context.args:
        await update.message.reply_text("Использование: /steps <task_id>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом.")
        return
    task = get_task(task_id)
    if task is None:
        await update.message.reply_text(f"Задача №{task_id} не найдена.")
        return
    lines = [f"Задача №{task_id}: {task['description']}"]
    if task.get("notes"):
        lines.append(f"Заметка: {task['notes']}")
    steps = get_steps(task_id)
    if not steps:
        lines.append("Подзадач нет.")
    else:
        lines.append("Подзадачи:")
        for s in steps:
            mark = "[x]" if s["completed"] else "[ ]"
            lines.append(f"  {mark} {s['id']}. {s['description']}")
    await update.message.reply_text("\n".join(lines))


async def _set_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE, done: bool
) -> None:
    if not context.args:
        cmd = "/stepdone" if done else "/stepundone"
        await update.message.reply_text(f"Использование: {cmd} <step_id>")
        return
    try:
        step_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID подзадачи должен быть числом.")
        return
    if mark_step_done(step_id, done):
        state = "выполнена" if done else "снова активна"
        await update.message.reply_text(f"Подзадача №{step_id} {state}.")
    else:
        await update.message.reply_text(f"Подзадача №{step_id} не найдена.")


async def stepdone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отмечает подзадачу выполненной: /stepdone <step_id>."""
    await _set_step(update, context, True)


async def stepundone_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Возвращает подзадачу в активные: /stepundone <step_id>."""
    await _set_step(update, context, False)


async def delstep_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаляет подзадачу: /delstep <step_id>."""
    if not context.args:
        await update.message.reply_text("Использование: /delstep <step_id>")
        return
    try:
        step_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID подзадачи должен быть числом.")
        return
    if delete_step(step_id):
        await update.message.reply_text(f"Подзадача №{step_id} удалена.")
    else:
        await update.message.reply_text(f"Подзадача №{step_id} не найдена.")


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает/устанавливает заметку: /note <task_id> [текст]."""
    if not context.args:
        await update.message.reply_text("Использование: /note <task_id> [текст]")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом.")
        return
    if len(context.args) == 1:
        task = get_task(task_id)
        if task is None:
            await update.message.reply_text(f"Задача №{task_id} не найдена.")
        elif task.get("notes"):
            await update.message.reply_text(
                f"Заметка №{task_id}: {task['notes']}"
            )
        else:
            await update.message.reply_text(f"У задачи №{task_id} нет заметки.")
        return
    note = " ".join(context.args[1:]).strip()
    if set_note(task_id, note):
        await update.message.reply_text(f"Заметка для №{task_id} сохранена.")
    else:
        await update.message.reply_text(f"Задача №{task_id} не найдена.")


async def delnote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаляет заметку: /delnote <task_id>."""
    if not context.args:
        await update.message.reply_text("Использование: /delnote <task_id>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID задачи должен быть числом.")
        return
    if set_note(task_id, None):
        await update.message.reply_text(f"Заметка задачи №{task_id} удалена.")
    else:
        await update.message.reply_text(f"Задача №{task_id} не найдена.")


async def myday_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """«Мой день»: /myday | /myday add <id> | /myday remove <id>."""
    user_id = update.effective_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    args = context.args or []
    if args and args[0] in ("add", "remove", "rm"):
        if len(args) < 2:
            await update.message.reply_text(
                "Использование: /myday add|remove <task_id>"
            )
            return
        try:
            task_id = int(args[1])
        except ValueError:
            await update.message.reply_text("ID задачи должен быть числом.")
            return
        if args[0] == "add":
            ok = add_to_myday(task_id, today)
            msg_ok = f"Задача №{task_id} добавлена в «Мой день»."
        else:
            ok = remove_from_myday(task_id)
            msg_ok = f"Задача №{task_id} убрана из «Мой день»."
        await update.message.reply_text(
            msg_ok if ok else f"Задача №{task_id} не найдена."
        )
        return
    tasks = get_myday(user_id, today)
    if not tasks:
        await update.message.reply_text("На сегодня в «Мой день» ничего нет.")
        return
    text = "Мой день:\n"
    for task in tasks:
        due_str = f", {task['due_date']}" if task["due_date"] else ""
        imp = "[важно] " if task.get("important") else ""
        text += f"• {task['id']}. {imp}{task['description']}{due_str}\n"
    await update.message.reply_text(text)


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
    application.add_handler(CommandHandler("lists", lists_command))
    application.add_handler(CommandHandler("newlist", newlist_command))
    application.add_handler(CommandHandler("renamelist", renamelist_command))
    application.add_handler(CommandHandler("dellist", dellist_command))
    application.add_handler(CommandHandler("movetask", movetask_command))
    application.add_handler(CommandHandler("repeat", repeat_command))
    application.add_handler(CommandHandler("important", important_command))
    application.add_handler(CommandHandler("unimportant", unimportant_command))
    application.add_handler(CommandHandler("addstep", addstep_command))
    application.add_handler(CommandHandler("steps", steps_command))
    application.add_handler(CommandHandler("stepdone", stepdone_command))
    application.add_handler(CommandHandler("stepundone", stepundone_command))
    application.add_handler(CommandHandler("delstep", delstep_command))
    application.add_handler(CommandHandler("note", note_command))
    application.add_handler(CommandHandler("delnote", delnote_command))
    application.add_handler(CommandHandler("myday", myday_command))

    # Планировщик напоминаний (APScheduler)
    setup_scheduler(application)

    # Запускаем бота и пропускаем все обновления, которые пришли, когда он был выключен
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':  # pragma: no cover
    main()

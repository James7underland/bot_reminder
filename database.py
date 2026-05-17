"""
Модуль для работы с базой данных SQLite.
"""
import calendar
import logging
import sqlite3
from datetime import datetime, timedelta

from config import DATABASE_PATH

RECURRENCES = ("daily", "weekly", "monthly", "yearly")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_connection():
    """Создает и возвращает соединение с базой данных. Включает поддержку внешних ключей."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Создаёт таблицу tasks и применяет миграции (идемпотентно)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            due_date TEXT,
            completed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reminder_sent INTEGER NOT NULL DEFAULT 0,
            list_id INTEGER,
            recurrence TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Миграции для БД, созданных до Фаз 4/5.2 (колонок могло не быть).
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(tasks)")}
    if "reminder_sent" not in columns:
        cursor.execute(
            "ALTER TABLE tasks ADD COLUMN reminder_sent INTEGER NOT NULL DEFAULT 0"
        )
    if "list_id" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN list_id INTEGER")
    if "recurrence" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN recurrence TEXT")
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована.")

def add_task(user_id: int, description: str, due_date: str | None = None) -> int:
    """
    Добавляет новую задачу.

    Args:
        user_id: ID пользователя в Telegram.
        description: Описание задачи.
        due_date: Дата и время напоминания в формате ISO (YYYY-MM-DD HH:MM:SS), опционально.

    Returns:
        ID новой задачи.

    Raises:
        sqlite3.Error: В случае ошибки базы данных.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tasks (user_id, description, due_date)
        VALUES (?, ?, ?)
    ''', (user_id, description, due_date))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Добавлена задача для user_id={user_id}: '{description}' (ID: {task_id})")
    return task_id

def get_tasks(user_id: int, completed: bool = False) -> list[dict]:
    """
    Возвращает список задач пользователя.

    Args:
        user_id: ID пользователя в Telegram.
        completed: Если True, возвращает выполненные задачи. Иначе - активные.

    Returns:
        Список словарей с данными задач.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row # Для доступа к полям по имени
    cursor = conn.cursor()

    flag = 1 if completed else 0
    cursor.execute(
        "SELECT * FROM tasks WHERE user_id = ? AND completed = ? ORDER BY created_at",
        (user_id, flag),
    )

    rows = cursor.fetchall()
    conn.close()

    # sqlite3.Row -> dict; completed приводим к Python bool (контракт тестов).
    result = []
    for row in rows:
        task = dict(row)
        task["completed"] = bool(task["completed"])
        result.append(task)
    return result

def mark_task_done(task_id: int) -> bool:
    """
    Отмечает задачу как выполненную.

    Args:
        task_id: ID задачи.

    Returns:
        True, если задача была найдена и обновлена, иначе False.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE tasks SET completed = 1 WHERE id = ?', (task_id,))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info(f"Задача ID={task_id} отмечена как выполненная.")
        return True
    else:
        logger.warning(f"Задача ID={task_id} не найдена при попытке отметить как выполненную.")
        return False

def set_reminder(task_id: int, due_date: str) -> bool:
    """
    Устанавливает или изменяет время напоминания для задачи.

    Args:
        task_id: ID задачи.
        due_date: Новое время напоминания в формате ISO.

    Returns:
        True, если задача была найдена и обновлена, иначе False.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET due_date = ?, reminder_sent = 0 WHERE id = ?",
        (due_date, task_id),
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info(f"Напоминание для задачи ID={task_id} установлено на {due_date}.")
        return True
    else:
        logger.warning(f"Задача ID={task_id} не найдена при установке напоминания.")
        return False


def get_due_tasks(now: str) -> list[dict]:
    """
    Задачи, для которых наступило время напоминания и оно ещё не отправлено.

    `now` — строка `YYYY-MM-DD HH:MM:SS` (тот же формат, что в `due_date`);
    лексикографическое сравнение для этого формата эквивалентно временно́му.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tasks WHERE completed = 0 AND reminder_sent = 0 "
        "AND due_date IS NOT NULL AND due_date <= ? ORDER BY due_date",
        (now,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_reminder_sent(task_id: int) -> bool:
    """Помечает напоминание задачи отправленным (анти-дубль)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET reminder_sent = 1 WHERE id = ?", (task_id,))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("reminder_sent=1 for task=%s", task_id)
        return True
    logger.warning("mark_reminder_sent: task=%s not found", task_id)
    return False


def update_task_description(task_id: int, description: str) -> bool:
    """Меняет описание задачи. False, если задачи нет."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET description = ? WHERE id = ?", (description, task_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s description updated", task_id)
        return True
    logger.warning("update_task_description: task=%s not found", task_id)
    return False


def mark_task_undone(task_id: int) -> bool:
    """Возвращает задачу в активные (completed=0). False, если задачи нет."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tasks SET completed = 0 WHERE id = ?", (task_id,))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s marked undone", task_id)
        return True
    logger.warning("mark_task_undone: task=%s not found", task_id)
    return False


# --- Списки/категории (Фаза 5.2) ---

def create_list(user_id: int, name: str) -> int:
    """Создаёт список и возвращает его id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO lists (user_id, name) VALUES (?, ?)", (user_id, name)
    )
    list_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info("user=%s created list=%s '%s'", user_id, list_id, name)
    return list_id


def get_lists(user_id: int) -> list[dict]:
    """Списки пользователя (по времени создания)."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM lists WHERE user_id = ? ORDER BY created_at, id",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def rename_list(list_id: int, name: str) -> bool:
    """Переименовывает список. False, если списка нет."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE lists SET name = ? WHERE id = ?", (name, list_id))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("list=%s renamed to '%s'", list_id, name)
        return True
    logger.warning("rename_list: list=%s not found", list_id)
    return False


def delete_list(list_id: int) -> bool:
    """Удаляет список; его задачи переносятся в «без списка» (list_id=NULL)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET list_id = NULL WHERE list_id = ?", (list_id,)
    )
    cursor.execute("DELETE FROM lists WHERE id = ?", (list_id,))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("list=%s deleted", list_id)
        return True
    logger.warning("delete_list: list=%s not found", list_id)
    return False


def assign_task_to_list(task_id: int, list_id: int | None) -> bool:
    """Привязывает задачу к списку (None = без списка). False, если задачи нет."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET list_id = ? WHERE id = ?", (list_id, task_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s assigned to list=%s", task_id, list_id)
        return True
    logger.warning("assign_task_to_list: task=%s not found", task_id)
    return False


def get_tasks_by_list(
    user_id: int, list_id: int | None, completed: bool = False
) -> list[dict]:
    """Активные/выполненные задачи пользователя в конкретном списке.

    `list_id=None` — задачи без списка.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    flag = 1 if completed else 0
    if list_id is None:
        cursor.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND completed = ? "
            "AND list_id IS NULL ORDER BY created_at",
            (user_id, flag),
        )
    else:
        cursor.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND completed = ? "
            "AND list_id = ? ORDER BY created_at",
            (user_id, flag, list_id),
        )
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        task = dict(row)
        task["completed"] = bool(task["completed"])
        result.append(task)
    return result


# --- Повторяющиеся задачи (Фаза 5.3) ---

def _add_months(dt: datetime, months: int) -> datetime:
    """Прибавляет месяцы, обрезая день до последнего дня целевого месяца."""
    total = dt.month - 1 + months
    year = dt.year + total // 12
    month = total % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def next_occurrence(due_date: str, recurrence: str) -> str:
    """Следующая дата повторения. due_date — `YYYY-MM-DD HH:MM:SS`."""
    dt = datetime.strptime(due_date, "%Y-%m-%d %H:%M:%S")
    if recurrence == "daily":
        nxt = dt + timedelta(days=1)
    elif recurrence == "weekly":
        nxt = dt + timedelta(days=7)
    elif recurrence == "monthly":
        nxt = _add_months(dt, 1)
    elif recurrence == "yearly":
        nxt = _add_months(dt, 12)
    else:
        raise ValueError(f"unknown recurrence: {recurrence}")
    return nxt.strftime("%Y-%m-%d %H:%M:%S")


def set_recurrence(task_id: int, recurrence: str | None) -> bool:
    """Задаёт повтор (None — снять). False при неверном значении/нет задачи."""
    if recurrence is not None and recurrence not in RECURRENCES:
        logger.warning("set_recurrence: invalid value %r", recurrence)
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET recurrence = ? WHERE id = ?", (recurrence, task_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s recurrence=%s", task_id, recurrence)
        return True
    logger.warning("set_recurrence: task=%s not found", task_id)
    return False


def complete_task(task_id: int) -> dict | None:
    """
    Выполняет задачу. Если задача повторяющаяся и имеет due_date —
    создаёт следующий экземпляр.

    Возвращает {completed, recurred, next_due, new_task_id} либо None,
    если задачи нет.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        logger.warning("complete_task: task=%s not found", task_id)
        return None

    cursor.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))

    recurred = False
    next_due = None
    new_task_id = None
    if row["recurrence"] in RECURRENCES and row["due_date"]:
        next_due = next_occurrence(row["due_date"], row["recurrence"])
        cursor.execute(
            "INSERT INTO tasks (user_id, description, due_date, list_id, "
            "recurrence) VALUES (?, ?, ?, ?, ?)",
            (
                row["user_id"],
                row["description"],
                next_due,
                row["list_id"],
                row["recurrence"],
            ),
        )
        new_task_id = cursor.lastrowid
        recurred = True

    conn.commit()
    conn.close()
    logger.info("task=%s completed (recurred=%s)", task_id, recurred)
    return {
        "completed": True,
        "recurred": recurred,
        "next_due": next_due,
        "new_task_id": new_task_id,
    }

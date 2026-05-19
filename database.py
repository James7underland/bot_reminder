"""
Модуль для работы с базой данных SQLite.
"""
import calendar
import logging
import re
import sqlite3
from datetime import datetime, timedelta

from config import DATABASE_PATH
from tzutil import valid_timezone

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
            recurrence TEXT,
            important INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            myday_date TEXT,
            remind_before INTEGER,
            deadline TEXT,
            reminder_at TEXT,
            overdue_notified INTEGER NOT NULL DEFAULT 0
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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            timezone TEXT NOT NULL DEFAULT 'UTC'
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
    if "important" not in columns:
        cursor.execute(
            "ALTER TABLE tasks ADD COLUMN important INTEGER NOT NULL DEFAULT 0"
        )
    if "notes" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN notes TEXT")
    if "myday_date" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN myday_date TEXT")
    if "remind_before" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN remind_before INTEGER")
    # Фаза 7: разделяем «срок» (deadline) и «напоминание» (reminder_at).
    if "reminder_at" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN reminder_at TEXT")
        # Раньше due_date был триггером напоминания — сохраняем поведение.
        cursor.execute(
            "UPDATE tasks SET reminder_at = due_date "
            "WHERE due_date IS NOT NULL"
        )
    if "deadline" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN deadline TEXT")
    if "overdue_notified" not in columns:
        cursor.execute(
            "ALTER TABLE tasks ADD COLUMN overdue_notified "
            "INTEGER NOT NULL DEFAULT 0"
        )
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

# Белый список сортировок (никакой пользовательский ввод не идёт в SQL).
_SORT_ORDERS = {
    "important": "important DESC, created_at",
    "due": "due_date IS NULL, due_date, created_at",
    "alpha": "description COLLATE NOCASE",
    "created": "created_at",
}


def get_tasks(
    user_id: int, completed: bool = False, sort: str | None = None
) -> list[dict]:
    """
    Возвращает список задач пользователя.

    Args:
        user_id: ID пользователя в Telegram.
        completed: Если True, возвращает выполненные задачи. Иначе - активные.
        sort: important | due | alpha | created. По умолчанию (None) —
            по времени создания (поведение неизменно).

    Returns:
        Список словарей с данными задач.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row # Для доступа к полям по имени
    cursor = conn.cursor()

    flag = 1 if completed else 0
    order = _SORT_ORDERS.get(sort, "created_at")
    cursor.execute(
        f"SELECT * FROM tasks WHERE user_id = ? AND completed = ? ORDER BY {order}",
        (user_id, flag),
    )

    rows = cursor.fetchall()
    conn.close()

    # sqlite3.Row -> dict; completed/important приводим к Python bool.
    result = []
    for row in rows:
        task = dict(row)
        task["completed"] = bool(task["completed"])
        task["important"] = bool(task["important"])
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

    `now` — строка `YYYY-MM-DD HH:MM:SS`. Учитывается `remind_before`
    (минуты до срока): время срабатывания =
    `due_date - remind_before` (при NULL — ровно `due_date`).
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tasks WHERE completed = 0 AND reminder_sent = 0 "
        "AND due_date IS NOT NULL "
        "AND datetime(due_date, '-' || COALESCE(remind_before, 0) "
        "|| ' minutes') <= ? ORDER BY due_date",
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


_WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
_EVERY_RE = re.compile(r"^every:([1-9]\d*):([dwmy])$")
_WEEKDAYS_RE = re.compile(r"^weekdays:([A-Z]{2}(?:,[A-Z]{2})*)$")


def _parse_weekdays(spec: str) -> set[int]:
    """`weekdays:MO,WE,FR` -> {0,2,4}. Бросает ValueError при мусоре."""
    m = _WEEKDAYS_RE.match(spec)
    if not m:
        raise ValueError(f"bad weekdays: {spec!r}")
    parts = m.group(1).split(",")
    days = {_WEEKDAYS.index(p) for p in parts if p in _WEEKDAYS}
    if len(days) != len(parts) or not days:
        raise ValueError(f"bad weekdays: {spec!r}")
    return days


def is_valid_recurrence(value: str | None) -> bool:
    """True для допустимых значений: None | пресеты | every:N:[dwmy] | weekdays:..."""
    if value is None or value in RECURRENCES:
        return True
    if _EVERY_RE.match(value):
        return True
    try:
        _parse_weekdays(value)
        return True
    except ValueError:
        return False


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
    elif (m := _EVERY_RE.match(recurrence)):
        n, unit = int(m.group(1)), m.group(2)
        if unit == "d":
            nxt = dt + timedelta(days=n)
        elif unit == "w":
            nxt = dt + timedelta(weeks=n)
        elif unit == "m":
            nxt = _add_months(dt, n)
        else:  # 'y'
            nxt = _add_months(dt, 12 * n)
    elif recurrence.startswith("weekdays:"):
        days = _parse_weekdays(recurrence)
        # Ищем ближайший день недели из набора (1..7 шагов вперёд)
        for step in range(1, 8):
            cand = dt + timedelta(days=step)
            if cand.weekday() in days:
                nxt = cand
                break
        else:  # pragma: no cover — defensive: набор всегда непуст
            raise ValueError(f"no weekday match: {recurrence}")
    else:
        raise ValueError(f"unknown recurrence: {recurrence}")
    return nxt.strftime("%Y-%m-%d %H:%M:%S")


def set_recurrence(task_id: int, recurrence: str | None) -> bool:
    """Задаёт повтор (None — снять). False при неверном значении/нет задачи."""
    if not is_valid_recurrence(recurrence):
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
    if row["recurrence"] and is_valid_recurrence(row["recurrence"]) and row["due_date"]:
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


# --- Важные задачи (Фаза 5.4) ---

def set_important(task_id: int, important: bool) -> bool:
    """Ставит/снимает флаг важности. False, если задачи нет."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET important = ? WHERE id = ?",
        (1 if important else 0, task_id),
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s important=%s", task_id, important)
        return True
    logger.warning("set_important: task=%s not found", task_id)
    return False


# --- Подзадачи и заметки (Фаза 5.5) ---

def get_task(task_id: int) -> dict | None:
    """Возвращает задачу по id (или None). completed/important -> bool."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    task = dict(row)
    task["completed"] = bool(task["completed"])
    task["important"] = bool(task["important"])
    return task


def add_step(task_id: int, description: str) -> int | None:
    """Добавляет подзадачу. None, если родительской задачи нет."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,))
    if cursor.fetchone() is None:
        conn.close()
        logger.warning("add_step: task=%s not found", task_id)
        return None
    cursor.execute(
        "INSERT INTO steps (task_id, description) VALUES (?, ?)",
        (task_id, description),
    )
    step_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info("task=%s add step=%s", task_id, step_id)
    return step_id


def get_steps(task_id: int) -> list[dict]:
    """Подзадачи задачи (по времени создания). completed -> bool."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM steps WHERE task_id = ? ORDER BY created_at, id",
        (task_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        step = dict(row)
        step["completed"] = bool(step["completed"])
        result.append(step)
    return result


def mark_step_done(step_id: int, done: bool = True) -> bool:
    """Отмечает подзадачу выполненной/невыполненной. False, если нет."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE steps SET completed = ? WHERE id = ?",
        (1 if done else 0, step_id),
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("step=%s done=%s", step_id, done)
        return True
    logger.warning("mark_step_done: step=%s not found", step_id)
    return False


def delete_step(step_id: int) -> bool:
    """Удаляет подзадачу. False, если её нет."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM steps WHERE id = ?", (step_id,))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("step=%s deleted", step_id)
        return True
    logger.warning("delete_step: step=%s not found", step_id)
    return False


def set_note(task_id: int, note: str | None) -> bool:
    """Задаёт заметку задачи (None — очистить). False, если задачи нет."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET notes = ? WHERE id = ?", (note, task_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s note set (%s chars)", task_id, len(note or ""))
        return True
    logger.warning("set_note: task=%s not found", task_id)
    return False


# --- «Мой день» (Фаза 5.6) ---

def add_to_myday(task_id: int, day: str) -> bool:
    """Закрепляет задачу в «Мой день» на дату `day` (YYYY-MM-DD)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET myday_date = ? WHERE id = ?", (day, task_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s myday=%s", task_id, day)
        return True
    logger.warning("add_to_myday: task=%s not found", task_id)
    return False


def remove_from_myday(task_id: int) -> bool:
    """Убирает задачу из «Мой день». False, если задачи нет."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET myday_date = NULL WHERE id = ?", (task_id,)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s removed from myday", task_id)
        return True
    logger.warning("remove_from_myday: task=%s not found", task_id)
    return False


def get_myday(user_id: int, day: str) -> list[dict]:
    """
    Задачи «на сегодня»: активные, у которых либо дедлайн в день `day`,
    либо они закреплены в «Мой день» на `day`.

    `day` — строка `YYYY-MM-DD`.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tasks WHERE user_id = ? AND completed = 0 AND ("
        "(due_date IS NOT NULL AND substr(due_date, 1, 10) = ?) "
        "OR myday_date = ?) ORDER BY due_date IS NULL, due_date, created_at",
        (user_id, day, day),
    )
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        task = dict(row)
        task["completed"] = bool(task["completed"])
        task["important"] = bool(task["important"])
        result.append(task)
    return result


# --- Поиск и гибкие напоминания (Фаза 5.7) ---

def search_tasks(user_id: int, query: str) -> list[dict]:
    """
    Активные задачи пользователя, где подстрока `query` встречается в
    описании или заметке (регистронезависимо, в т.ч. для кириллицы —
    фильтрация на стороне Python через str.lower()).
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tasks WHERE user_id = ? AND completed = 0 "
        "ORDER BY created_at",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    result = []
    for row in rows:
        task = dict(row)
        haystack = f"{task['description']}\n{task['notes'] or ''}".lower()
        if q in haystack:
            task["completed"] = bool(task["completed"])
            task["important"] = bool(task["important"])
            result.append(task)
    return result


def set_remind_before(task_id: int, minutes: int | None) -> bool:
    """
    Задаёт напоминание за `minutes` минут до срока (None — ровно в срок).
    False при отрицательном значении или если задачи нет.
    """
    if minutes is not None and minutes < 0:
        logger.warning("set_remind_before: negative minutes %s", minutes)
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET remind_before = ? WHERE id = ?", (minutes, task_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s remind_before=%s", task_id, minutes)
        return True
    logger.warning("set_remind_before: task=%s not found", task_id)
    return False


# --- Часовые пояса пользователя (Фаза 5.8) ---

def get_timezone(user_id: int) -> str:
    """Часовой пояс пользователя (IANA). По умолчанию — UTC."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timezone FROM user_settings WHERE user_id = ?", (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "UTC"


def set_timezone(user_id: int, timezone: str) -> bool:
    """Сохраняет часовой пояс пользователя. False, если зона неверная."""
    if not valid_timezone(timezone):
        logger.warning("set_timezone: invalid tz %r", timezone)
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_settings (user_id, timezone) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET timezone = excluded.timezone",
        (user_id, timezone),
    )
    conn.commit()
    conn.close()
    logger.info("user=%s timezone=%s", user_id, timezone)
    return True


# --- Срок (deadline) и напоминание (reminder_at) — Фаза 7 ---

def set_deadline(task_id: int, deadline: str | None) -> bool:
    """
    Ставит/снимает срок задачи (UTC, `YYYY-MM-DD HH:MM:SS`).
    Сбрасывает `overdue_notified` (новый срок → можно снова уведомить).
    False, если задачи нет.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET deadline = ?, overdue_notified = 0 WHERE id = ?",
        (deadline, task_id),
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s deadline=%s", task_id, deadline)
        return True
    logger.warning("set_deadline: task=%s not found", task_id)
    return False


def set_reminder_at(task_id: int, reminder_at: str | None) -> bool:
    """
    Ставит/снимает время напоминания (UTC, `YYYY-MM-DD HH:MM:SS`).
    Сбрасывает `reminder_sent`. False, если задачи нет.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET reminder_at = ?, reminder_sent = 0 WHERE id = ?",
        (reminder_at, task_id),
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s reminder_at=%s", task_id, reminder_at)
        return True
    logger.warning("set_reminder_at: task=%s not found", task_id)
    return False


def get_due_reminders(now: str) -> list[dict]:
    """
    Активные задачи, у которых наступило `reminder_at` и напоминание ещё
    не отправлено. `now` — UTC `YYYY-MM-DD HH:MM:SS`.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tasks WHERE completed = 0 AND reminder_sent = 0 "
        "AND reminder_at IS NOT NULL AND reminder_at <= ? "
        "ORDER BY reminder_at",
        (now,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_overdue_tasks(now: str) -> list[dict]:
    """
    Активные задачи, у которых срок прошёл и о просрочке ещё не
    уведомляли. `now` — UTC `YYYY-MM-DD HH:MM:SS`.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tasks WHERE completed = 0 AND overdue_notified = 0 "
        "AND deadline IS NOT NULL AND deadline < ? ORDER BY deadline",
        (now,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_overdue_notified(task_id: int) -> bool:
    """Помечает, что об просрочке задачи уже уведомили. False, если нет."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE tasks SET overdue_notified = 1 WHERE id = ?", (task_id,)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("task=%s overdue_notified=1", task_id)
        return True
    logger.warning("mark_overdue_notified: task=%s not found", task_id)
    return False

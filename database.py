"""
Модуль для работы с базой данных SQLite.
"""
import calendar
import logging
import re
import sqlite3
from datetime import UTC, datetime, timedelta

from config import DATABASE_PATH
from tzutil import valid_timezone

RECURRENCES = ("daily", "weekly", "monthly", "yearly")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_connection():
    """
    Создаёт соединение с БД. Включает:
    - `foreign_keys=ON` — каскадное удаление;
    - `journal_mode=WAL` — несколько читателей + один писатель
      параллельно. Снимает контеншн между `bot_reminder` (планировщик)
      и `bot_webapp` (HTTP API), которые пишут в одну БД и без WAL
      периодически блокировали друг друга, проявляясь в Mini App как
      «зависшая» менюшка (запросы зависали на блокировке БД).
    - `busy_timeout=5000` — ждать до 5 сек на залоченных страницах
      вместо мгновенного `OperationalError: database is locked`.
    WAL устанавливается единожды и сохраняется в самом файле БД —
    повторный PRAGMA на каждом коннекте дёшев (no-op, если уже WAL).
    """
    conn = sqlite3.connect(DATABASE_PATH, timeout=5.0)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
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
            overdue_notified INTEGER NOT NULL DEFAULT 0,
            order_index INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#0088CC',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
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
    # Фаза 9.4: ручной порядок задач. Бэкфилл по `id` сохраняет исходный
    # порядок (id монотонный, как и created_at). Новые задачи получают
    # max(order_index)+1 в add_task.
    if "order_index" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN order_index INTEGER")
        cursor.execute(
            "UPDATE tasks SET order_index = id WHERE order_index IS NULL"
        )
    # Фаза 9.5: цвет списка (визуальная подсказка в Mini App).
    list_columns = {row[1] for row in cursor.execute("PRAGMA table_info(lists)")}
    if "color" not in list_columns:
        cursor.execute(
            "ALTER TABLE lists ADD COLUMN color TEXT NOT NULL "
            "DEFAULT '#0088CC'"
        )
    # Фаза 10.7: soft-delete для списков (с поддержкой undo).
    if "deleted_at" not in list_columns:
        cursor.execute("ALTER TABLE lists ADD COLUMN deleted_at TEXT")
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
    # Фаза 9.4: order_index = max(order_index of same user) + 1, чтобы новая
    # задача шла последней в ручной сортировке (как в Microsoft To Do).
    cursor.execute(
        "INSERT INTO tasks (user_id, description, due_date, order_index) "
        "VALUES (?, ?, ?, "
        "COALESCE((SELECT MAX(order_index) FROM tasks WHERE user_id = ?), 0) + 1)",
        (user_id, description, due_date, user_id),
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Добавлена задача для user_id={user_id}: '{description}' (ID: {task_id})")
    return task_id

# Белый список сортировок (никакой пользовательский ввод не идёт в SQL).
# С Фазы 9.4 дефолт — ручной порядок (`order_index`, потом `created_at` как
# тайбрейкер для старых бэкфилл-нулей и одинаковых индексов).
_SORT_ORDERS = {
    "important": "important DESC, order_index, created_at",
    "due": "due_date IS NULL, due_date, order_index, created_at",
    "alpha": "description COLLATE NOCASE",
    "created": "created_at",
    "manual": "order_index, created_at",
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
    # Дефолт (None) — ручной порядок (Фаза 9.4), чтобы Mini App и /tasks
    # отражали drag/стрелки. Старая семантика «по created_at» доступна как
    # sort="created".
    order = _SORT_ORDERS.get(sort, "order_index, created_at")
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


def get_lists(user_id: int, include_deleted: bool = False) -> list[dict]:
    """
    Списки пользователя (по времени создания). По умолчанию исключает
    soft-deleted (Phase 10.7). `include_deleted=True` нужен только для
    эндпоинта восстановления / cron-purge.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if include_deleted:
        cursor.execute(
            "SELECT * FROM lists WHERE user_id = ? ORDER BY created_at, id",
            (user_id,),
        )
    else:
        cursor.execute(
            "SELECT * FROM lists WHERE user_id = ? AND deleted_at IS NULL "
            "ORDER BY created_at, id",
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


_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def is_valid_color(value: str | None) -> bool:
    """`#RRGGBB` или None (None=сброс к дефолту через отдельную ветку)."""
    return bool(value and _HEX_COLOR_RE.match(value))


def set_list_color(list_id: int, color: str) -> bool:
    """Задаёт цвет списка (#RRGGBB). False — если цвет невалидный или нет."""
    if not is_valid_color(color):
        logger.warning("set_list_color: bad color %r", color)
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE lists SET color = ? WHERE id = ?", (color, list_id)
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("list=%s color=%s", list_id, color)
        return True
    logger.warning("set_list_color: list=%s not found", list_id)
    return False


def delete_list(list_id: int) -> bool:
    """
    Soft-delete списка (Phase 10.7): помечает `deleted_at = now()`, но
    физически не удаляет. Задачи СОХРАНЯЮТ `list_id` (на время окна
    отмены, чтобы restore вернул всё на места). Если уже удалён —
    повторно False (idempotency).

    Реальное удаление выполняет `purge_deleted_lists()` через 24 ч.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE lists SET deleted_at = CURRENT_TIMESTAMP "
        "WHERE id = ? AND deleted_at IS NULL",
        (list_id,),
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("list=%s soft-deleted", list_id)
        return True
    logger.warning("delete_list: list=%s not found or already deleted", list_id)
    return False


def restore_list(list_id: int) -> bool:
    """
    Phase 10.7: отменяет soft-delete. Возвращает True, если список был
    в состоянии deleted (и теперь восстановлен). False — если списка
    нет, или он и так активен.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE lists SET deleted_at = NULL "
        "WHERE id = ? AND deleted_at IS NOT NULL",
        (list_id,),
    )
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info("list=%s restored", list_id)
        return True
    logger.warning("restore_list: list=%s not found or not deleted", list_id)
    return False


def purge_deleted_lists(older_than_hours: int = 24) -> int:
    """
    Phase 10.7: физическое удаление списков, помеченных как deleted
    дольше `older_than_hours` часов. Их задачи отвязываются
    (`list_id=NULL`) — то же поведение, что было раньше у hard-delete.
    Возвращает число удалённых списков. Вызывается из APScheduler
    раз в час (см. `scheduler.py`).
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        # Находим id'шники, чтобы отвязать их задачи.
        cursor.execute(
            "SELECT id FROM lists WHERE deleted_at IS NOT NULL AND "
            "datetime(deleted_at) <= datetime('now', ?)",
            (f"-{int(older_than_hours)} hours",),
        )
        ids = [row[0] for row in cursor.fetchall()]
        if not ids:
            conn.rollback()
            conn.close()
            return 0
        placeholders = ",".join("?" * len(ids))
        cursor.execute(
            f"UPDATE tasks SET list_id = NULL WHERE list_id IN ({placeholders})",
            ids,
        )
        cursor.execute(
            f"DELETE FROM lists WHERE id IN ({placeholders})", ids
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    logger.info("purge_deleted_lists: removed %d list(s)", len(ids))
    return len(ids)


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
            "AND list_id IS NULL ORDER BY order_index, created_at",
            (user_id, flag),
        )
    else:
        cursor.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND completed = ? "
            "AND list_id = ? ORDER BY order_index, created_at",
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


def get_steps_counts(user_id: int) -> dict[int, dict[str, int]]:
    """
    Агрегат по подзадачам всех задач пользователя:
    `{task_id: {"done": N, "total": M}}`. Один SQL-запрос (GROUP BY) —
    чтобы избежать N+1 при отрисовке списка. Задачи без подзадач
    в результат не попадают (Mini App просто не рисует «N/M»).
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT s.task_id, COUNT(*) AS total, "
        "SUM(CASE WHEN s.completed = 1 THEN 1 ELSE 0 END) AS done "
        "FROM steps s JOIN tasks t ON t.id = s.task_id "
        "WHERE t.user_id = ? GROUP BY s.task_id",
        (user_id,),
    )
    result = {row[0]: {"done": int(row[2] or 0), "total": int(row[1])}
              for row in cursor.fetchall()}
    conn.close()
    return result


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


# --- Smart-views (Фаза 9.2) ---

def _rows_to_tasks(rows) -> list[dict]:
    out = []
    for row in rows:
        t = dict(row)
        t["completed"] = bool(t["completed"])
        t["important"] = bool(t["important"])
        out.append(t)
    return out


def get_planned(user_id: int) -> list[dict]:
    """Активные задачи с дедлайном или напоминанием. Срок раньше — выше."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tasks WHERE user_id = ? AND completed = 0 "
        "AND (deadline IS NOT NULL OR reminder_at IS NOT NULL) "
        "ORDER BY deadline IS NULL, deadline, "
        "reminder_at IS NULL, reminder_at, created_at",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return _rows_to_tasks(rows)


def get_important_tasks(user_id: int) -> list[dict]:
    """Активные важные задачи. Срок раньше — выше."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tasks WHERE user_id = ? AND completed = 0 "
        "AND important = 1 ORDER BY deadline IS NULL, deadline, created_at",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return _rows_to_tasks(rows)


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


def snooze_reminder(task_id: int, minutes: int) -> bool:
    """
    Откладывает напоминание на `minutes` минут от ТЕКУЩЕГО UTC-времени
    (а не от старого `reminder_at`) — это семантика «напомни через…».
    Сбрасывает `reminder_sent` (повторно сработает). False при minutes<=0
    или если задачи нет.
    """
    if minutes <= 0:
        logger.warning("snooze_reminder: bad minutes %s", minutes)
        return False
    now = datetime.now(UTC).replace(tzinfo=None)
    new_at = (now + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    return set_reminder_at(task_id, new_at)


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


# --- Ручной порядок задач (Фаза 9.4) ---

def _move_task(task_id: int, direction: int) -> bool:
    """
    direction = -1 (вверх) или +1 (вниз). Меняется местами с ближайшим
    активным «соседом» того же пользователя в том же списке (включая
    «без списка», когда list_id IS NULL). False, если задачи нет, она
    выполнена, или соседа в этом направлении не существует (крайняя).
    Per-user `order_index` уникален (см. `add_task`), поэтому простого
    свопа двух значений достаточно — без сдвига промежутка.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, user_id, list_id, order_index, completed "
        "FROM tasks WHERE id = ?",
        (task_id,),
    )
    row = cursor.fetchone()
    if row is None or row["completed"]:
        conn.close()
        logger.warning("_move_task: task=%s missing or completed", task_id)
        return False
    user_id, list_id, idx = row["user_id"], row["list_id"], row["order_index"]
    # Сосед — активная задача того же пользователя в том же списке (или
    # тоже «без списка»), с минимально большим/меньшим order_index.
    if list_id is None:
        list_clause = "AND list_id IS NULL"
        params: tuple = (user_id, idx)
    else:
        list_clause = "AND list_id = ?"
        params = (user_id, idx, list_id)
    if direction < 0:
        cursor.execute(
            f"SELECT id, order_index FROM tasks WHERE user_id = ? "
            f"AND completed = 0 AND order_index < ? {list_clause} "
            "ORDER BY order_index DESC, id DESC LIMIT 1",
            params,
        )
    else:
        cursor.execute(
            f"SELECT id, order_index FROM tasks WHERE user_id = ? "
            f"AND completed = 0 AND order_index > ? {list_clause} "
            "ORDER BY order_index, id LIMIT 1",
            params,
        )
    neigh = cursor.fetchone()
    if neigh is None:
        conn.close()
        return False
    cursor.execute(
        "UPDATE tasks SET order_index = ? WHERE id = ?",
        (neigh["order_index"], task_id),
    )
    cursor.execute(
        "UPDATE tasks SET order_index = ? WHERE id = ?", (idx, neigh["id"])
    )
    conn.commit()
    conn.close()
    logger.info(
        "task=%s moved %s (swap with %s)",
        task_id, "up" if direction < 0 else "down", neigh["id"],
    )
    return True


def move_task_up(task_id: int) -> bool:
    """Меняет местами задачу с предыдущим активным соседом того же списка."""
    return _move_task(task_id, -1)


def move_task_down(task_id: int) -> bool:
    """Меняет местами задачу со следующим активным соседом того же списка."""
    return _move_task(task_id, 1)


def reorder_task(task_id: int, after_task_id: int | None) -> bool:
    """
    Phase 10.6 (drag-and-drop): помещает `task_id` сразу после
    `after_task_id` среди активных задач того же пользователя в том же
    списке. `after_task_id=None` — двигает в начало. Если `after_task_id`
    отсутствует/принадлежит другому юзеру или списку — False.

    Внутри: одна транзакция. Достаём всех активных «соседей» (user_id,
    list_id), убираем `task_id` из их последовательности, вставляем в
    нужное место, перенумеровываем `order_index = i+1`. Простая
    линейная сложность — на практике задач немного.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT user_id, list_id, completed FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None or row["completed"]:
            return False
        user_id, list_id = row["user_id"], row["list_id"]
        # Берём только активных соседей (выполненные не отображаются и
        # не должны влиять на порядок). Сортировка стабильна по
        # текущему order_index, потом по created_at, потом по id.
        if list_id is None:
            cursor.execute(
                "SELECT id FROM tasks WHERE user_id = ? AND completed = 0 "
                "AND list_id IS NULL "
                "ORDER BY order_index, created_at, id",
                (user_id,),
            )
        else:
            cursor.execute(
                "SELECT id FROM tasks WHERE user_id = ? AND completed = 0 "
                "AND list_id = ? "
                "ORDER BY order_index, created_at, id",
                (user_id, list_id),
            )
        ids = [r["id"] for r in cursor.fetchall()]
        if task_id not in ids:
            return False
        ids.remove(task_id)
        if after_task_id is None:
            ids.insert(0, task_id)
        else:
            if after_task_id not in ids:
                # Соседа нет в той же подгруппе → отвергаем.
                return False
            pos = ids.index(after_task_id) + 1
            ids.insert(pos, task_id)
        # Записываем новые order_index одной транзакцией.
        cursor.execute("BEGIN")
        for new_idx, tid in enumerate(ids, start=1):
            cursor.execute(
                "UPDATE tasks SET order_index = ? WHERE id = ?",
                (new_idx, tid),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    logger.info(
        "task=%s reordered after=%s (user=%s list=%s)",
        task_id, after_task_id, user_id, list_id,
    )
    return True


# --- Здоровье / статистика (Фаза 10.3) ---

def db_ping() -> bool:
    """
    Лёгкая проверка БД: открыть соединение и сделать `SELECT 1`.
    True — БД отвечает. False — любая ошибка (соединения нет, лок
    дольше busy_timeout, повреждение и т.д.). Используется `/healthz`
    для внешнего мониторинга.
    """
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return cursor.fetchone()[0] == 1
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning("db_ping failed: %s", e)
        return False


def get_global_counts() -> dict[str, int]:
    """
    Сводные счётчики по всей БД (не на пользователя): tasks_total,
    tasks_active, lists_total, users. Используется `/healthz` для
    подтверждения, что данные не утеряны после деплоя/рестарта.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks")
        tasks_total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE completed = 0")
        tasks_active = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM lists")
        lists_total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM tasks")
        users = cursor.fetchone()[0]
    finally:
        conn.close()
    return {
        "tasks_total": tasks_total,
        "tasks_active": tasks_active,
        "lists_total": lists_total,
        "users": users,
    }


def get_user_stats(user_id: int) -> dict:
    """
    Сводка по одному пользователю — для виджета в Mini App. Один проход
    по БД (несколько коротких SELECT'ов, BUSY_TIMEOUT их обслужит).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND completed = 0",
            (user_id,),
        )
        active = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND completed = 1",
            (user_id,),
        )
        completed = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM lists WHERE user_id = ?", (user_id,)
        )
        lists_n = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ? AND completed = 0 "
            "AND important = 1", (user_id,),
        )
        important = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM steps s JOIN tasks t ON t.id = s.task_id "
            "WHERE t.user_id = ? AND s.completed = 0", (user_id,),
        )
        steps_open = cursor.fetchone()[0]
        cursor.execute(
            "SELECT MIN(created_at) FROM tasks "
            "WHERE user_id = ? AND completed = 0", (user_id,),
        )
        oldest = cursor.fetchone()[0]
    finally:
        conn.close()
    return {
        "active": active,
        "completed": completed,
        "lists": lists_n,
        "important": important,
        "steps_open": steps_open,
        "oldest_open_at": oldest,
    }


# --- Экспорт / импорт (Фаза 10.2) ---

EXPORT_VERSION = 1

# Поля задачи, которые попадают в экспорт. ID и user_id опускаются:
# при импорте задачи получают новые ID, чтобы не конфликтовать с
# существующими данными. order_index сохраняется (восстанавливает порядок).
_EXPORT_TASK_FIELDS = (
    "description", "due_date", "completed", "created_at",
    "reminder_sent", "recurrence", "important", "notes", "myday_date",
    "remind_before", "deadline", "reminder_at", "overdue_notified",
    "order_index",
)


def export_user_data(user_id: int) -> dict:
    """
    Полный снимок данных пользователя — для бэкапа/переноса. Один
    проход по БД: список списков, задачи (с привязкой к именам списков,
    а не id, чтобы импорт мог их пересоздать), подзадачи внутри каждой
    задачи, настройки. Версия схемы — `EXPORT_VERSION`.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Списки
    cursor.execute(
        "SELECT id, name, color, created_at FROM lists "
        "WHERE user_id = ? ORDER BY created_at, id",
        (user_id,),
    )
    lists_rows = cursor.fetchall()
    id_to_name = {row["id"]: row["name"] for row in lists_rows}
    lists = [{"name": r["name"], "color": r["color"],
              "created_at": r["created_at"]} for r in lists_rows]
    # Задачи
    cursor.execute(
        "SELECT * FROM tasks WHERE user_id = ? "
        "ORDER BY order_index, created_at, id",
        (user_id,),
    )
    task_rows = cursor.fetchall()
    tasks: list[dict] = []
    task_ids: list[int] = []
    for r in task_rows:
        t = {k: r[k] for k in _EXPORT_TASK_FIELDS}
        # list_id → list_name (None для «без списка»)
        t["list_name"] = id_to_name.get(r["list_id"])
        # Совместимость с дефолтом WAL/CREATE: важный/выполнено как bool.
        t["completed"] = bool(t["completed"])
        t["important"] = bool(t["important"])
        t["_id"] = r["id"]
        tasks.append(t)
        task_ids.append(r["id"])
    # Подзадачи. Запрашиваем разом, фильтруем по списку id.
    steps_by_task: dict[int, list[dict]] = {tid: [] for tid in task_ids}
    if task_ids:
        placeholders = ",".join("?" * len(task_ids))
        cursor.execute(
            "SELECT task_id, description, completed, created_at "
            f"FROM steps WHERE task_id IN ({placeholders}) "
            "ORDER BY task_id, created_at, id",
            task_ids,
        )
        for srow in cursor.fetchall():
            steps_by_task[srow["task_id"]].append({
                "description": srow["description"],
                "completed": bool(srow["completed"]),
                "created_at": srow["created_at"],
            })
    # Прикрепляем подзадачи к задачам и убираем внутренний `_id`.
    for t in tasks:
        t["steps"] = steps_by_task.get(t.pop("_id"), [])
    # Настройки пользователя
    cursor.execute(
        "SELECT timezone FROM user_settings WHERE user_id = ?", (user_id,)
    )
    tz_row = cursor.fetchone()
    tz = tz_row["timezone"] if tz_row else "UTC"
    conn.close()
    return {
        "version": EXPORT_VERSION,
        "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user": {"id": user_id, "timezone": tz},
        "lists": lists,
        "tasks": tasks,
    }


def _validate_export_payload(payload: dict) -> str | None:
    """Возвращает строку с ошибкой, либо None если payload валиден."""
    if not isinstance(payload, dict):
        return "payload must be an object"
    ver = payload.get("version")
    if ver != EXPORT_VERSION:
        return f"unsupported version (expected {EXPORT_VERSION}, got {ver!r})"
    if not isinstance(payload.get("lists"), list):
        return "missing 'lists' array"
    if not isinstance(payload.get("tasks"), list):
        return "missing 'tasks' array"
    return None


def import_user_data(
    user_id: int, payload: dict, *, mode: str = "merge"
) -> dict:
    """
    Импортирует данные из формата `export_user_data`.

    `mode="merge"` — добавляет новые задачи и списки рядом с существующими
    (списки сопоставляются по имени; новые задачи дозаписываются,
    дубликаты не отсеиваются — пользователь сам решит, что удалить).
    `mode="replace"` — сначала удаляет все списки/задачи/подзадачи
    пользователя, потом импортирует.

    Возвращает `{"lists": N, "tasks": M, "steps": K}` — счётчики добавленных
    записей. Поднимает `ValueError` при невалидном payload — caller (API
    эндпоинт) переводит его в HTTP 422.
    """
    err = _validate_export_payload(payload)
    if err:
        raise ValueError(err)
    if mode not in {"merge", "replace"}:
        raise ValueError(f"bad mode: {mode!r}")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        if mode == "replace":
            # FK ON DELETE CASCADE на steps → удалятся вместе с задачами.
            cursor.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM lists WHERE user_id = ?", (user_id,))

        # Списки: имя → id, переиспользуем существующие в merge.
        # Soft-deleted списки (Phase 10.7) НЕ переиспользуем — пользователь
        # их явно удалил, импорт должен создать новый.
        cursor.execute(
            "SELECT id, name FROM lists WHERE user_id = ? "
            "AND deleted_at IS NULL",
            (user_id,),
        )
        name_to_id = {row[1]: row[0] for row in cursor.fetchall()}
        lists_added = 0
        for lst in payload["lists"]:
            name = (lst.get("name") or "").strip()
            if not name:
                continue
            if name in name_to_id:
                continue
            color = lst.get("color") or "#0088CC"
            if not is_valid_color(color):
                color = "#0088CC"
            cursor.execute(
                "INSERT INTO lists (user_id, name, color) VALUES (?, ?, ?)",
                (user_id, name, color),
            )
            name_to_id[name] = cursor.lastrowid
            lists_added += 1

        # Задачи + подзадачи. order_index пересчитываем относительно
        # текущего max'а пользователя, чтобы импорт не конфликтовал с
        # уже существующими номерами в merge-режиме.
        cursor.execute(
            "SELECT COALESCE(MAX(order_index), 0) FROM tasks "
            "WHERE user_id = ?", (user_id,),
        )
        base_idx = cursor.fetchone()[0] or 0
        tasks_added = 0
        steps_added = 0
        for i, t in enumerate(payload["tasks"], start=1):
            if not isinstance(t, dict):
                continue
            description = (t.get("description") or "").strip()
            if not description:
                continue
            list_id = name_to_id.get(t.get("list_name")) if t.get("list_name") else None
            new_order = base_idx + i
            cursor.execute(
                "INSERT INTO tasks (user_id, description, due_date, "
                "completed, created_at, reminder_sent, list_id, "
                "recurrence, important, notes, myday_date, remind_before, "
                "deadline, reminder_at, overdue_notified, order_index) "
                "VALUES (?,?,?,?,COALESCE(?, CURRENT_TIMESTAMP),?,?,?,?,?,?,?,?,?,?,?)",
                (
                    user_id, description, t.get("due_date"),
                    1 if t.get("completed") else 0, t.get("created_at"),
                    1 if t.get("reminder_sent") else 0, list_id,
                    t.get("recurrence"),
                    1 if t.get("important") else 0, t.get("notes"),
                    t.get("myday_date"), t.get("remind_before"),
                    t.get("deadline"), t.get("reminder_at"),
                    1 if t.get("overdue_notified") else 0, new_order,
                ),
            )
            new_task_id = cursor.lastrowid
            tasks_added += 1
            for step in (t.get("steps") or []):
                sdesc = (step.get("description") or "").strip()
                if not sdesc:
                    continue
                cursor.execute(
                    "INSERT INTO steps (task_id, description, completed, "
                    "created_at) VALUES (?, ?, ?, "
                    "COALESCE(?, CURRENT_TIMESTAMP))",
                    (new_task_id, sdesc,
                     1 if step.get("completed") else 0,
                     step.get("created_at")),
                )
                steps_added += 1

        # Часовой пояс — только если в payload явно задан и
        # отличается от UTC по умолчанию.
        user_info = payload.get("user") or {}
        tz = (user_info.get("timezone") or "").strip()
        if tz and valid_timezone(tz):
            cursor.execute(
                "INSERT INTO user_settings (user_id, timezone) "
                "VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET timezone=?",
                (user_id, tz, tz),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    logger.info(
        "import user=%s mode=%s lists=%d tasks=%d steps=%d",
        user_id, mode, lists_added, tasks_added, steps_added,
    )
    return {"lists": lists_added, "tasks": tasks_added, "steps": steps_added}

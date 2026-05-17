"""
Модуль для работы с базой данных SQLite.
"""
import logging
import sqlite3

from config import DATABASE_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_connection():
    """Создает и возвращает соединение с базой данных. Включает поддержку внешних ключей."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Инициализирует базу данных, создавая таблицу tasks, если она не существует."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            due_date TEXT,
            completed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
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
    cursor.execute('UPDATE tasks SET due_date = ? WHERE id = ?', (due_date, task_id))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    if rows_affected > 0:
        logger.info(f"Напоминание для задачи ID={task_id} установлено на {due_date}.")
        return True
    else:
        logger.warning(f"Задача ID={task_id} не найдена при установке напоминания.")
        return False

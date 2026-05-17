"""
Тесты для модуля database.py, использующие pytest.
"""
from database import add_task, get_tasks, mark_task_done, set_reminder


def test_add_task_success():
    """Тестирует успешное добавление задачи."""
    task_id = add_task(123, "Test task description")
    assert isinstance(task_id, int)
    assert task_id > 0

    # Проверяем, что задача действительно добавилась
    tasks = get_tasks(123)
    assert len(tasks) == 1
    assert tasks[0]['description'] == "Test task description"
    assert tasks[0]['due_date'] is None
    assert tasks[0]['completed'] is False

def test_add_task_with_due_date():
    """Тестирует добавление задачи с указанием времени напоминания."""
    due_date = "2026-05-18 10:00:00"
    add_task(456, "Task with reminder", due_date)

    tasks = get_tasks(456)
    assert tasks[0]['due_date'] == due_date

def test_get_tasks_returns_only_user_tasks():
    """Тестирует, что get_tasks возвращает задачи только для указанного пользователя."""
    # Добавляем задачи для двух пользователей
    add_task(100, "User 100 task")
    add_task(200, "User 200 task")

    # Проверяем, что пользователь 100 видит только свою задачу
    user_100_tasks = get_tasks(100)
    assert len(user_100_tasks) == 1
    assert user_100_tasks[0]['user_id'] == 100

    # Проверяем, что пользователь 200 видит только свою задачу
    user_200_tasks = get_tasks(200)
    assert len(user_200_tasks) == 1
    assert user_200_tasks[0]['user_id'] == 200

def test_get_tasks_returns_only_active_tasks():
    """Тестирует, что get_tasks по умолчанию возвращает только активные (не выполненные) задачи."""
    task_id = add_task(300, "Active task")
    # Отмечаем задачу как выполненную
    mark_task_done(task_id)

    # Добавляем еще одну активную
    add_task(300, "Another active task")

    # Получаем активные задачи
    active_tasks = get_tasks(300)
    assert len(active_tasks) == 1 # Только одна активная
    assert active_tasks[0]['description'] == "Another active task"

def test_mark_task_done_success():
    """Тестирует успешное отметку задачи как выполненной."""
    task_id = add_task(500, "Task to complete")

    result = mark_task_done(task_id)
    assert result is True

    # Проверяем, что задача теперь помечена как выполненная
    tasks = get_tasks(500, completed=True) # Получаем выполненные
    assert len(tasks) == 1
    assert tasks[0]['completed'] is True

def test_mark_task_done_nonexistent_id():
    """Тестирует попытку отметить как выполненную несуществующую задачу."""
    result = mark_task_done(999999) # ID, которого нет
    assert result is False # Должно вернуть False

def test_set_reminder_success():
    """Тестирует успешную установку напоминания."""
    task_id = add_task(600, "Task for reminder")
    new_due_date = "2026-05-19 15:30:00"

    result = set_reminder(task_id, new_due_date)
    assert result is True

    # Проверяем, что due_date обновился
    tasks = get_tasks(600)
    assert tasks[0]['due_date'] == new_due_date

def test_set_reminder_nonexistent_id():
    """Тестирует попытку установить напоминание для несуществующей задачи."""
    result = set_reminder(999999, "2026-05-20 10:00:00")
    assert result is False # Должно вернуть False

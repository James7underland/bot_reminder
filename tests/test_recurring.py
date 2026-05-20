"""Фаза 5.3: тесты повторяющихся задач (БД-слой).

С Phase 11.1 чат-команды убраны — тесты их хендлеров тоже.
"""
import pytest

from database import (
    add_task,
    complete_task,
    get_tasks,
    is_valid_recurrence,
    next_occurrence,
    set_recurrence,
)

# --- next_occurrence ---

@pytest.mark.parametrize(
    "due, rec, expected",
    [
        ("2026-05-17 09:00:00", "daily", "2026-05-18 09:00:00"),
        ("2026-05-17 09:00:00", "weekly", "2026-05-24 09:00:00"),
        ("2026-01-15 10:00:00", "monthly", "2026-02-15 10:00:00"),
        ("2026-01-31 10:00:00", "monthly", "2026-02-28 10:00:00"),  # clamp
        ("2026-12-31 10:00:00", "monthly", "2027-01-31 10:00:00"),  # rollover
        ("2026-05-17 09:00:00", "yearly", "2027-05-17 09:00:00"),
        ("2024-02-29 09:00:00", "yearly", "2025-02-28 09:00:00"),  # leap clamp
    ],
)
def test_next_occurrence(due, rec, expected):
    assert next_occurrence(due, rec) == expected


def test_next_occurrence_invalid():
    with pytest.raises(ValueError):
        next_occurrence("2026-05-17 09:00:00", "hourly")


# --- set_recurrence ---

def test_set_recurrence_lifecycle():
    tid = add_task(1, "t")
    assert set_recurrence(tid, "daily") is True
    assert get_tasks(1)[0]["recurrence"] == "daily"
    assert set_recurrence(tid, None) is True
    assert get_tasks(1)[0]["recurrence"] is None


def test_set_recurrence_invalid_value():
    tid = add_task(1, "t")
    assert set_recurrence(tid, "bogus") is False


def test_set_recurrence_nonexistent():
    assert set_recurrence(999999, "daily") is False


# --- complete_task ---

def test_complete_task_nonrecurring():
    tid = add_task(1, "x")
    res = complete_task(tid)
    assert res == {
        "completed": True,
        "recurred": False,
        "next_due": None,
        "new_task_id": None,
    }
    assert get_tasks(1) == []
    assert [t["id"] for t in get_tasks(1, completed=True)] == [tid]


def test_complete_task_nonexistent():
    assert complete_task(999999) is None


def test_complete_task_recurring_spawns_next():
    tid = add_task(1, "standup", "2026-05-17 09:00:00")
    set_recurrence(tid, "daily")

    res = complete_task(tid)

    assert res["recurred"] is True
    assert res["next_due"] == "2026-05-18 09:00:00"
    assert isinstance(res["new_task_id"], int)

    active = get_tasks(1)
    assert len(active) == 1
    nxt = active[0]
    assert nxt["id"] == res["new_task_id"]
    assert nxt["description"] == "standup"
    assert nxt["due_date"] == "2026-05-18 09:00:00"
    assert nxt["recurrence"] == "daily"
    assert [t["id"] for t in get_tasks(1, completed=True)] == [tid]


def test_complete_task_recurring_without_due_does_not_spawn():
    tid = add_task(1, "no due")
    set_recurrence(tid, "weekly")
    res = complete_task(tid)
    assert res["recurred"] is False
    assert get_tasks(1) == []


# --- Фаза 9.1: custom recurrence ---

@pytest.mark.parametrize(
    "due, rec, expected",
    [
        ("2026-05-17 09:00:00", "every:2:d", "2026-05-19 09:00:00"),
        ("2026-05-17 09:00:00", "every:3:w", "2026-06-07 09:00:00"),
        ("2026-01-15 10:00:00", "every:2:m", "2026-03-15 10:00:00"),
        ("2026-01-31 10:00:00", "every:1:m", "2026-02-28 10:00:00"),  # clamp
        ("2024-02-29 09:00:00", "every:1:y", "2025-02-28 09:00:00"),  # leap
        # weekdays: понедельник 2026-05-18 → следующий Wed(2026-05-20) или Fri
        ("2026-05-18 09:00:00", "weekdays:WE,FR", "2026-05-20 09:00:00"),
        # пятница 2026-05-22 → следующий из {MO} = понедельник 2026-05-25
        ("2026-05-22 09:00:00", "weekdays:MO", "2026-05-25 09:00:00"),
        # воскресенье 2026-05-24 → MO следующего дня
        ("2026-05-24 09:00:00", "weekdays:MO,WE,FR", "2026-05-25 09:00:00"),
    ],
)
def test_custom_recurrence_next(due, rec, expected):
    assert next_occurrence(due, rec) == expected


@pytest.mark.parametrize(
    "rec",
    ["every:0:d", "every:abc:d", "every:2:x", "weekdays:", "weekdays:XX",
     "weekdays:MO,MO", "weekly:custom", "garbage"],
)
def test_is_valid_recurrence_rejects_garbage(rec):
    assert is_valid_recurrence(rec) is False


def test_is_valid_recurrence_accepts():
    for v in (None, "daily", "weekly", "monthly", "yearly",
              "every:1:d", "every:5:w", "weekdays:MO", "weekdays:MO,WE,FR"):
        assert is_valid_recurrence(v) is True


def test_set_recurrence_accepts_custom():
    tid = add_task(1, "t")
    assert set_recurrence(tid, "every:2:d") is True
    assert get_tasks(1)[0]["recurrence"] == "every:2:d"
    assert set_recurrence(tid, "weekdays:MO,WE,FR") is True
    assert get_tasks(1)[0]["recurrence"] == "weekdays:MO,WE,FR"


def test_complete_task_with_custom_recurrence_spawns_next():
    tid = add_task(1, "standup", "2026-05-17 09:00:00")  # Sunday
    set_recurrence(tid, "weekdays:MO,WE,FR")  # next = Monday
    res = complete_task(tid)
    assert res["next_due"] == "2026-05-18 09:00:00"
    assert get_tasks(1)[0]["recurrence"] == "weekdays:MO,WE,FR"

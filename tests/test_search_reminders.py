"""Фаза 5.7: тесты поиска и гибких напоминаний (БД-слой).

С Phase 11.1 чат-команды убраны.
"""
from database import (
    add_task,
    get_due_tasks,
    get_task,
    mark_task_done,
    search_tasks,
    set_note,
    set_remind_before,
)

# --- search_tasks ---

def test_search_empty_query():
    add_task(1, "что-то")
    assert search_tasks(1, "   ") == []


def test_search_in_description_case_insensitive():
    t = add_task(1, "Купить молоко")
    add_task(1, "Помыть машину")
    assert [x["id"] for x in search_tasks(1, "молоко")] == [t]
    assert [x["id"] for x in search_tasks(1, "МОЛОКО")] == [t]


def test_search_in_notes():
    t = add_task(1, "Задача")
    set_note(t, "позвонить врачу завтра")
    assert [x["id"] for x in search_tasks(1, "врач")] == [t]


def test_search_excludes_completed_and_other_users():
    done = add_task(1, "найди меня done")
    mark_task_done(done)
    add_task(2, "найди меня other")
    assert search_tasks(1, "найди меня") == []


# --- set_remind_before ---

def test_set_remind_before_lifecycle():
    t = add_task(1, "t", "2026-05-17 12:00:00")
    assert set_remind_before(t, 30) is True
    assert get_task(t)["remind_before"] == 30
    assert set_remind_before(t, None) is True
    assert get_task(t)["remind_before"] is None


def test_set_remind_before_negative_and_missing():
    t = add_task(1, "t")
    assert set_remind_before(t, -1) is False
    assert set_remind_before(999999, 10) is False


# --- get_due_tasks учитывает remind_before ---

def test_due_with_remind_before_triggers_early():
    t = add_task(1, "meeting", "2026-05-17 12:00:00")
    set_remind_before(t, 30)  # сработать в 11:30
    assert [x["id"] for x in get_due_tasks("2026-05-17 11:30:00")] == [t]
    assert get_due_tasks("2026-05-17 11:29:00") == []


def test_due_without_remind_before_unchanged():
    t = add_task(1, "plain", "2026-05-17 12:00:00")
    assert get_due_tasks("2026-05-17 11:59:00") == []
    assert [x["id"] for x in get_due_tasks("2026-05-17 12:00:00")] == [t]



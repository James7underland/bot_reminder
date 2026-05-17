"""Тесты чистой функции parse_add_command (без Telegram/БД)."""
import pytest

from bot import parse_add_command


@pytest.mark.parametrize(
    "text, expected",
    [
        ("/add Купить молоко", ("Купить молоко", None)),
        ("/add Сделать отчёт 2026-05-18 15:00", ("Сделать отчёт", "2026-05-18 15:00:00")),
        ("/add Встреча 18.05.2026 09:30", ("Встреча", "2026-05-18 09:30:00")),
        ("/add@my_bot Задача 2026-01-02 03:04", ("Задача", "2026-01-02 03:04:00")),
        ("/add 2026-05-18 15:00 Позвонить маме", ("Позвонить маме", "2026-05-18 15:00:00")),
        # дата-подобный, но невалидный токен → не дата
        ("/add Дедлайн 2026-13-40 99:99", ("Дедлайн 2026-13-40 99:99", None)),
        ("/add", ("", None)),
        ("/add     ", ("", None)),
        # без префикса /add тоже разбирается
        ("Купить хлеб 2026-05-18 15:00", ("Купить хлеб", "2026-05-18 15:00:00")),
    ],
)
def test_parse_add_command(text, expected):
    assert parse_add_command(text) == expected


def test_parse_collapses_inner_whitespace():
    desc, due = parse_add_command("/add Позвонить   2026-05-18 15:00   врачу")
    assert due == "2026-05-18 15:00:00"
    assert desc == "Позвонить врачу"


def test_parse_handles_empty_input():
    assert parse_add_command("") == ("", None)


def test_parse_dotted_date_normalised_to_iso():
    assert parse_add_command("/add X 31.12.2026 23:59") == ("X", "2026-12-31 23:59:00")

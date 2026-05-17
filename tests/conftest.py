"""
Конфигурация pytest.

Фикстура даёт КАЖДОМУ тесту свежую файловую SQLite-базу во временной
директории (function-scope) и патчит путь к БД в модуле `database`.

Почему не `:memory:`: `database.get_connection()` открывает новое
соединение на каждый вызов. У SQLite `:memory:` своя БД на каждое
соединение — таблица, созданная в `init_db()`, не видна последующим
вызовам (`no such table: tasks`). Временный файл живёт между соединениями
и при этом изолирован по тесту.
"""
from unittest.mock import patch

import pytest

import database


@pytest.fixture(autouse=True)
def test_db(tmp_path):
    """Свежая изолированная БД на каждый тест."""
    db_file = tmp_path / "test_tasks.db"
    with patch.object(database, "DATABASE_PATH", str(db_file)):
        database.init_db()
        yield

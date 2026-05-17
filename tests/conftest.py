"""
Файл конфигурации для pytest.
"""
import pytest
from unittest.mock import patch
# Импортируем функцию инициализации из database.py
from database import init_db

# Путь к временной базе данных в памяти
TEST_DB_PATH = ":memory:"

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Фикстура для инициализации тестовой базы данных перед запуском тестов."""
    # Подменяем путь к базе данных на :memory:
    with patch('config.DATABASE_PATH', TEST_DB_PATH), \
         patch('database.DATABASE_PATH', TEST_DB_PATH):
        # Инициализируем базу данных
        init_db()
        yield # Выполняем тесты
        # Здесь можно добавить код для очистки, если нужно
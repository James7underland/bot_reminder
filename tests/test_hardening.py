"""Фаза 6a: тесты харденинга (глобальный error-handler)."""
import logging
from unittest.mock import MagicMock

import bot


async def test_error_handler_logs_exception(caplog):
    ctx = MagicMock()
    ctx.error = RuntimeError("boom")
    with caplog.at_level(logging.ERROR):
        await bot.error_handler(object(), ctx)
    assert "Unhandled exception" in caplog.text
    assert "boom" in caplog.text

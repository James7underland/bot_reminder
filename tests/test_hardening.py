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


def test_quiet_third_party_loggers_hides_token_logs():
    # httpx на INFO печатает URL Telegram API с токеном — недопустимо.
    logging.getLogger("httpx").setLevel(logging.INFO)
    bot.quiet_third_party_loggers()
    for name in ("httpx", "httpcore", "apscheduler", "telegram"):
        assert logging.getLogger(name).level == logging.WARNING

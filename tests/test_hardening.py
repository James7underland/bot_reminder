"""Фаза 6a: тесты харденинга (глобальный error-handler) + Phase 11.1
тесты тонкого bot.py (только запуск Mini App)."""
import logging
from unittest.mock import AsyncMock, MagicMock

import bot


async def test_error_handler_logs_exception(caplog):
    ctx = MagicMock()
    ctx.error = RuntimeError("boom")
    with caplog.at_level(logging.ERROR):
        await bot.error_handler(object(), ctx)
    assert "Unhandled error" in caplog.text
    assert "boom" in caplog.text


def test_quiet_third_party_loggers_hides_token_logs():
    # httpx на INFO печатает URL Telegram API с токеном — недопустимо.
    logging.getLogger("httpx").setLevel(logging.INFO)
    bot.quiet_third_party_loggers()
    for name in ("httpx", "httpcore", "apscheduler", "telegram"):
        assert logging.getLogger(name).level == logging.WARNING


# --- Phase 11.1: тонкий bot.py ---

def _mk_update(text=None, web_app_data=None):
    u = MagicMock()
    u.effective_message = MagicMock()
    u.effective_message.reply_text = AsyncMock()
    u.effective_message.text = text
    u.effective_message.web_app_data = web_app_data
    return u


async def test_start_replies_with_webapp_button():
    u = _mk_update()
    await bot.start(u, MagicMock())
    u.effective_message.reply_text.assert_awaited_once()
    args, kwargs = u.effective_message.reply_text.call_args
    assert "Mini App" in args[0]
    # reply_markup должен содержать ReplyKeyboard с WebApp-кнопкой.
    kb = kwargs["reply_markup"]
    btn = kb.keyboard[0][0]
    assert btn.web_app is not None and btn.web_app.url.startswith("https://")


async def test_start_no_message_is_noop():
    """Без `effective_message` не падаем (например, channel_post)."""
    u = MagicMock()
    u.effective_message = None
    await bot.start(u, MagicMock())   # просто не должно бросить


async def test_fallback_text_redirects_to_miniapp():
    u = _mk_update(text="что-то странное")
    await bot.fallback_text(u, MagicMock())
    u.effective_message.reply_text.assert_awaited_once()
    text = u.effective_message.reply_text.call_args.args[0]
    assert "Mini App" in text


async def test_fallback_text_ignores_webapp_data():
    """Сообщения от WebApp (data) не должны провоцировать редирект-ответ."""
    u = _mk_update(web_app_data=object())
    await bot.fallback_text(u, MagicMock())
    u.effective_message.reply_text.assert_not_awaited()


async def test_fallback_text_no_message_is_noop():
    u = MagicMock()
    u.effective_message = None
    await bot.fallback_text(u, MagicMock())   # не должно бросить


# --- Phase 11.3: whitelist в боте ---

async def test_start_denies_user_not_in_allowlist(monkeypatch):
    import config as config_mod
    monkeypatch.setattr(config_mod, "ALLOWED_USER_IDS", {99})
    monkeypatch.setattr(config_mod, "ALLOWED_USERNAMES", set())
    u = _mk_update()
    u.effective_user = MagicMock()
    u.effective_user.id = 42
    u.effective_user.username = "stranger"
    await bot.start(u, MagicMock())
    u.effective_message.reply_text.assert_awaited_once()
    assert "ограничен" in u.effective_message.reply_text.call_args.args[0]


async def test_start_allows_user_in_allowlist(monkeypatch):
    import config as config_mod
    monkeypatch.setattr(config_mod, "ALLOWED_USER_IDS", set())
    monkeypatch.setattr(config_mod, "ALLOWED_USERNAMES", {"e_rnst"})
    u = _mk_update()
    u.effective_user = MagicMock()
    u.effective_user.id = 42
    u.effective_user.username = "e_rnst"
    await bot.start(u, MagicMock())
    # Получил приветствие с WebApp-кнопкой
    args, kwargs = u.effective_message.reply_text.call_args
    assert "Mini App" in args[0]
    assert kwargs.get("reply_markup") is not None


async def test_fallback_denies_user_not_in_allowlist(monkeypatch):
    import config as config_mod
    monkeypatch.setattr(config_mod, "ALLOWED_USER_IDS", {99})
    monkeypatch.setattr(config_mod, "ALLOWED_USERNAMES", set())
    u = _mk_update(text="any text")
    u.effective_user = MagicMock()
    u.effective_user.id = 42
    u.effective_user.username = "stranger"
    await bot.fallback_text(u, MagicMock())
    assert "ограничен" in u.effective_message.reply_text.call_args.args[0]

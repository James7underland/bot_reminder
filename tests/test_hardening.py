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
    # httpx на INFO печатает URL Telegram API с токеном – недопустимо.
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
    # Phase 11.3b: ReplyKeyboard заменён на InlineKeyboard (передаёт
    # initData на tdesktop, в отличие от ReplyKeyboard).
    u = _mk_update()
    u.effective_chat = MagicMock()
    u.effective_chat.id = 12345
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.set_chat_menu_button = AsyncMock()
    await bot.start(u, ctx)
    u.effective_message.reply_text.assert_awaited_once()
    args, kwargs = u.effective_message.reply_text.call_args
    assert "Mini App" in args[0]
    # reply_markup – InlineKeyboardMarkup с WebApp-кнопкой.
    kb = kwargs["reply_markup"]
    btn = kb.inline_keyboard[0][0]
    assert btn.web_app is not None and btn.web_app.url.startswith("https://")
    # chat menu button установлен программно.
    ctx.bot.set_chat_menu_button.assert_awaited_once()


async def test_start_survives_set_chat_menu_button_failure(caplog):
    """`set_chat_menu_button` иногда падает (например, бот без админ-прав
    в группе); /start всё равно отвечает приветствием."""
    import logging
    u = _mk_update()
    u.effective_chat = MagicMock()
    u.effective_chat.id = 1
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.set_chat_menu_button = AsyncMock(
        side_effect=RuntimeError("simulated"))
    with caplog.at_level(logging.WARNING):
        await bot.start(u, ctx)
    u.effective_message.reply_text.assert_awaited_once()
    assert any("set_chat_menu_button failed" in m for m in caplog.messages)


async def test_start_no_message_is_noop():
    """Без `effective_message` не падаем (например, channel_post)."""
    u = MagicMock()
    u.effective_message = None
    await bot.start(u, MagicMock())   # просто не должно бросить


async def test_fallback_text_redirects_to_miniapp():
    u = _mk_update(text="что-то странное")
    await bot.fallback_text(u, MagicMock())
    u.effective_message.reply_text.assert_awaited_once()
    args, kwargs = u.effective_message.reply_text.call_args
    text = args[0]
    # Phase 11.4: краткий текст с указанием кнопок (без фразы про Mini App).
    assert "кнопку ниже" in text and "Открыть" in text
    # InlineKeyboardMarkup с WebApp-кнопкой обязателен.
    kb = kwargs["reply_markup"]
    assert kb.inline_keyboard[0][0].web_app is not None


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
    u.effective_chat = MagicMock()
    u.effective_chat.id = 42
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.set_chat_menu_button = AsyncMock()
    await bot.start(u, ctx)
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


# --- Phase 11.7: callback-кнопки в уведомлениях ---

def _mk_callback_update(data, user_id=42):
    """Удобный mock для CallbackQuery."""
    u = MagicMock()
    u.effective_user = MagicMock()
    u.effective_user.id = user_id
    u.effective_user.username = "u"
    q = MagicMock()
    q.data = data
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    u.callback_query = q
    return u, q


async def test_callback_snooze_shifts_reminder():
    import config as config_mod
    save_ids = config_mod.ALLOWED_USER_IDS
    config_mod.ALLOWED_USER_IDS = set()
    try:
        from database import add_task, get_task, set_reminder_at
        tid = add_task(42, "drink water")
        set_reminder_at(tid, "2020-01-01 00:00:00")
        u, q = _mk_callback_update(f"snz:{tid}:15")
        await bot.reminder_callback(u, MagicMock())
        q.answer.assert_awaited_once()
        q.edit_message_text.assert_awaited_once()
        # reminder_at сдвинут в будущее (>= 2024)
        assert get_task(tid)["reminder_at"] > "2024"
    finally:
        config_mod.ALLOWED_USER_IDS = save_ids


async def test_callback_done_completes_task():
    import config as config_mod
    save_ids = config_mod.ALLOWED_USER_IDS
    config_mod.ALLOWED_USER_IDS = set()
    try:
        from database import add_task, get_task
        tid = add_task(42, "do it")
        u, q = _mk_callback_update(f"done:{tid}")
        await bot.reminder_callback(u, MagicMock())
        q.edit_message_text.assert_awaited_once()
        text = q.edit_message_text.call_args.args[0]
        assert "Выполнено" in text and "do it" in text
        assert get_task(tid)["completed"] is True
    finally:
        config_mod.ALLOWED_USER_IDS = save_ids


async def test_callback_rejects_foreign_task():
    """Нельзя дёрнуть чужую задачу через подделанный callback_data."""
    import config as config_mod
    save_ids = config_mod.ALLOWED_USER_IDS
    config_mod.ALLOWED_USER_IDS = set()
    try:
        from database import add_task, get_task
        # Задача другого пользователя
        tid = add_task(99, "their task")
        # Юзер 42 пытается её завершить
        u, q = _mk_callback_update(f"done:{tid}", user_id=42)
        await bot.reminder_callback(u, MagicMock())
        q.answer.assert_awaited_once()
        q.edit_message_text.assert_not_awaited()
        assert get_task(tid)["completed"] is False  # не тронута
    finally:
        config_mod.ALLOWED_USER_IDS = save_ids


async def test_callback_garbage_data_silent():
    """Кривые callback_data не ломают обработчик."""
    for data in (None, "", "snz:abc:15", "done:notanint", "weird:1"):
        u, q = _mk_callback_update(data)
        await bot.reminder_callback(u, MagicMock())
        # `answer` мог быть либо вызван, либо нет (если q.data пуст);
        # главное – обработчик не упал и не отредактировал.
        q.edit_message_text.assert_not_awaited()


async def test_callback_denied_for_disallowed_user(monkeypatch):
    import config as config_mod
    monkeypatch.setattr(config_mod, "ALLOWED_USER_IDS", {99})
    monkeypatch.setattr(config_mod, "ALLOWED_USERNAMES", set())
    from database import add_task, get_task
    tid = add_task(42, "x")
    u, q = _mk_callback_update(f"done:{tid}", user_id=42)
    await bot.reminder_callback(u, MagicMock())
    # whitelist отверг – задача не закрыта
    assert get_task(tid)["completed"] is False
    q.edit_message_text.assert_not_awaited()

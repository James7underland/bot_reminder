"""
Главный модуль Telegram-бота.

С Phase 11.1 бот не отвечает на команды (вся работа со списком —
в Mini App). Сохранены только:
- `/start` — приветствие с кнопкой запуска Mini App;
- `/help` — то же сообщение (для пользователей, привыкших к /help);
- авто-ответ на любое другое сообщение — «Используй Mini App ↓»;
- планировщик `setup_scheduler` — рассылает напоминания и
  уведомления о просрочке, физически чистит soft-deleted (Phase 10.7).
"""
import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import MINI_APP_URL, TELEGRAM_BOT_TOKEN, is_user_allowed
from database import init_db
from logsetup import setup_logging
from scheduler import setup_scheduler

# Совместимость с тестами (`test_bot.py::test_quiet_third_party_loggers`).
_NOISY_LOGGERS = ("httpx", "httpcore", "apscheduler", "telegram")


def quiet_third_party_loggers() -> None:
    """Поднимает уровень шумных сторонних логгеров до WARNING.

    Сохранено для обратной совместимости с тестами; реальная настройка
    делается через `logsetup.setup_logging`.
    """
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


setup_logging("bot")
logger = logging.getLogger(__name__)


# --- Хендлеры ---

def _miniapp_inline_keyboard() -> InlineKeyboardMarkup:
    """
    Phase 11.3b: InlineKeyboardButton с `web_app=...` — единственный
    надёжный способ запустить Mini App из чата с передачей `initData`.

    ReplyKeyboard-кнопка (предыдущая попытка) на Telegram Desktop
    открывает Mini App без подписи (`initData=""`), отсюда 401.
    Inline-кнопка работает идентично «верхней» menu-button.
    """
    btn = InlineKeyboardButton(
        text="📋 Открыть список задач",
        web_app=WebAppInfo(url=MINI_APP_URL),
    )
    return InlineKeyboardMarkup([[btn]])


_WELCOME_TEXT = (
    "Привет! Я бот-напоминалка.\n\n"
    "Все задачи, списки и заметки — в Mini App. Нажми кнопку "
    "ниже или 📋 «Открыть» вверху чата, чтобы его запустить.\n\n"
    "Напоминания о задачах я буду присылать сюда автоматически."
)


async def _ensure_chat_menu_button(context: ContextTypes.DEFAULT_TYPE,
                                    chat_id: int) -> None:
    """
    Phase 11.3b: программно задаём верхнюю кнопку «Открыть» (chat menu
    button) → MINI_APP_URL. Это та кнопка, которая видна слева от поля
    ввода. Она запускается без диалога и всегда передаёт initData.
    Если уже установлена — `setChatMenuButton` всё равно идемпотентна.
    """
    try:
        await context.bot.set_chat_menu_button(
            chat_id=chat_id,
            menu_button=MenuButtonWebApp(
                text="📋 Открыть",
                web_app=WebAppInfo(url=MINI_APP_URL),
            ),
        )
    except Exception as e:    # не валим /start, если TG API ругнулся
        logger.warning("set_chat_menu_button failed for chat=%s: %s",
                       chat_id, e)


def _user_allowed(update: Update) -> bool:
    """Phase 11.3: проверяет allowlist по `effective_user`."""
    u = update.effective_user
    if u is None:
        return False
    return is_user_allowed(u.id, u.username)


_DENIED_TEXT = "Доступ к этому боту ограничен. Если это ошибка — обратись к владельцу."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/start` и `/help` — одно и то же приветствие с WebApp-кнопкой."""
    if update.effective_message is None:
        return
    if not _user_allowed(update):
        logger.warning(
            "access denied (chat): user_id=%s username=%s",
            getattr(update.effective_user, "id", None),
            getattr(update.effective_user, "username", None),
        )
        await update.effective_message.reply_text(_DENIED_TEXT)
        return
    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id is not None:
        await _ensure_chat_menu_button(context, chat_id)
    await update.effective_message.reply_text(
        _WELCOME_TEXT, reply_markup=_miniapp_inline_keyboard()
    )


async def fallback_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Любое НЕ-командное сообщение → короткий ответ с кнопкой Mini App.
    Без этого хендлера пользователи, привыкшие писать команды бота
    словами, не понимали бы, что бот их не обрабатывает.
    """
    msg = update.effective_message
    if msg is None:
        return
    # Сообщения от WebApp (data) не считаются обычным текстом.
    if msg.web_app_data is not None:
        return
    if not _user_allowed(update):
        await msg.reply_text(_DENIED_TEXT)
        return
    await msg.reply_text(
        "Нажми кнопку ниже или 📋 «Открыть» вверху чата.",
        reply_markup=_miniapp_inline_keyboard(),
    )


async def error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Логирует исключения PTB, не падая."""
    logger.exception(
        "Unhandled error: %s", context.error,
        exc_info=context.error,
    )


# --- Запуск (исключён из coverage, требует Telegram-сети) ---

def main() -> None:  # pragma: no cover
    """Запускает бота (сетевой polling — вне unit-тестов)."""
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN не задан. Скопируйте .env.example в .env "
            "и укажите токен от @BotFather."
        )
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    init_db()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    # Любой не-командный текст / голос / фото / документ → fallback.
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, fallback_text)
    )
    application.add_error_handler(error_handler)

    # Планировщик: напоминания + purge soft-deleted списков (Phase 10.7).
    setup_scheduler(application)

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':  # pragma: no cover
    main()

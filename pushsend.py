"""
Phase 13.1: отправка Web Push уведомлений (`pywebpush`).

`pywebpush` импортируется лениво — без VAPID-ключей или библиотеки
функция `send_push_to_user` тихо превращается в no-op (TG-канал и
foreground-polling всё ещё работают). Это позволяет деплоить webapp
без push-зависимости, добавлять её постепенно.

VAPID-ключи генерируются один раз. Команда генерации — в DEPLOYMENT.md;
кратко: `vapid --gen` от пакета `py-vapid` (входит в `pywebpush`).
"""
import json
import logging

import config
from database import list_push_subscriptions, remove_push_subscription

logger = logging.getLogger(__name__)


def push_enabled() -> bool:
    """True если VAPID настроен И библиотека установлена."""
    if not config.VAPID_PUBLIC_KEY or not config.VAPID_PRIVATE_KEY:
        return False
    try:
        import pywebpush  # noqa: F401
        return True
    except ImportError:
        return False


def send_push_to_user(
    user_id: int, title: str, body: str, *,
    channel: str = "app", task_id: int | None = None,
) -> int:
    """
    Шлёт push на все подписки пользователя. Возвращает число успешных
    доставок. Не падает — все ошибки логируются, проблемная подписка
    удаляется (если push-сервис вернул 404/410 Gone).
    """
    if not push_enabled():
        return 0
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return 0

    subs = list_push_subscriptions(user_id)
    if not subs:
        return 0

    # Полезная нагрузка для service worker: title + body + meta для
    # выбора отображения (channel=alarm → requireInteraction + vibrate).
    payload = json.dumps({
        "title": title,
        "body": body,
        "channel": channel,
        "task_id": task_id,
    }, ensure_ascii=False)

    vapid_claims = {"sub": config.VAPID_SUBJECT}
    delivered = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=payload,
                vapid_private_key=config.VAPID_PRIVATE_KEY,
                vapid_claims=vapid_claims,
                ttl=3600,
            )
            delivered += 1
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                # Подписка устарела → удаляем, больше не пробуем.
                remove_push_subscription(sub["endpoint"])
                logger.info("push: subscription gone (%s), removed", status)
            else:
                logger.warning(
                    "push: send failed user=%s status=%s err=%s",
                    user_id, status, e,
                )
        except Exception as e:
            logger.warning("push: unexpected error user=%s: %s", user_id, e)
    return delivered

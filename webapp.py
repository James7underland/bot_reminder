"""
HTTP API для Telegram Mini App (Фаза 8).

`validate_init_data` — чистая, тестируемая проверка подписи Telegram
WebApp `initData` (авторизация). FastAPI-приложение `app` раздаёт REST
поверх функций `database`, фронтенд монтируется в Фазе 8.2.
"""
import hashlib
import hmac
import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import parse_qsl

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from database import (
    RECURRENCES,
    add_step,
    add_task,
    add_to_myday,
    complete_task,
    create_list,
    delete_step,
    get_lists,
    get_myday,
    get_steps,
    get_task,
    get_tasks,
    get_tasks_by_list,
    get_timezone,
    init_db,
    mark_step_done,
    mark_task_undone,
    remove_from_myday,
    set_deadline,
    set_important,
    set_note,
    set_recurrence,
    set_reminder_at,
    update_task_description,
)
from tzutil import to_local, to_utc

logger = logging.getLogger(__name__)

_TIME_FMT = "%Y-%m-%d %H:%M:%S"


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Проверяет подпись Telegram WebApp `initData`.

    Возвращает dict пользователя (с `id`) при валидной подписи, иначе
    None. Алгоритм — по докам Telegram: secret = HMAC_SHA256("WebAppData",
    token); hash = HMAC_SHA256(secret, data_check_string).
    """
    if not init_data or not bot_token:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash or "user" not in pairs:
        return None
    data_check_string = "\n".join(
        f"{k}={pairs[k]}" for k in sorted(pairs)
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    calc_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(calc_hash, received_hash):
        return None
    try:
        user = json.loads(pairs["user"])
    except (ValueError, TypeError):
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    return user


async def current_user_id(x_init_data: str = Header(default="")) -> int:
    """FastAPI-зависимость: валидирует initData из заголовка X-Init-Data."""
    user = validate_init_data(x_init_data, config.TELEGRAM_BOT_TOKEN or "")
    if user is None:
        raise HTTPException(status_code=401, detail="invalid init data")
    return int(user["id"])


def _now_utc() -> str:
    return datetime.now(UTC).replace(tzinfo=None).strftime(_TIME_FMT)


def _to_utc_or_none(value: str | None, user_id: int) -> str | None:
    """Локальное 'YYYY-MM-DD HH:MM[:SS]' пользователя → UTC-строка."""
    if not value:
        return None
    v = value.strip()
    if len(v) == 16:  # без секунд
        v += ":00"
    return to_utc(v, get_timezone(user_id))


def _today_local(user_id: int) -> str:
    """Сегодняшняя дата в часовом поясе пользователя ('YYYY-MM-DD')."""
    return to_local(_now_utc(), get_timezone(user_id))[:10]


def _decorate(task: dict, now: str) -> dict:
    """Добавляет вычисляемый флаг `overdue` (срок прошёл, не выполнено)."""
    dl = task.get("deadline")
    task["overdue"] = bool(
        dl and not task["completed"] and dl < now
    )
    return task


def _require_own_task(user_id: int, task_id: int) -> dict:
    task = get_task(task_id)
    if task is None or task["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="task not found")
    return task


class TaskCreate(BaseModel):
    description: str
    deadline: str | None = None
    reminder_at: str | None = None


class TaskPatch(BaseModel):
    description: str | None = None
    important: bool | None = None
    deadline: str | None = None
    reminder_at: str | None = None
    clear_deadline: bool = False
    clear_reminder: bool = False
    recurrence: str | None = None
    clear_recurrence: bool = False
    notes: str | None = None
    clear_notes: bool = False


class ListCreate(BaseModel):
    name: str


class MyDayToggle(BaseModel):
    on: bool = True


class StepCreate(BaseModel):
    description: str


class StepToggle(BaseModel):
    done: bool = True


@asynccontextmanager
async def _lifespan(_app: FastAPI):  # pragma: no cover
    init_db()
    yield


app = FastAPI(title="Reminder Mini App API", lifespan=_lifespan)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.get("/api/tasks")
async def api_tasks(
    user_id: int = Depends(current_user_id),
    list_id: int | None = None,
    completed: bool = False,
) -> list[dict]:
    if list_id is None:
        tasks = get_tasks(user_id, completed=completed)
    else:
        real = None if list_id == 0 else list_id
        tasks = get_tasks_by_list(user_id, real, completed=completed)
    now = _now_utc()
    return [_decorate(t, now) for t in tasks]


@app.post("/api/tasks")
async def api_create_task(
    body: TaskCreate, user_id: int = Depends(current_user_id)
) -> dict:
    desc = body.description.strip()
    if not desc:
        raise HTTPException(status_code=422, detail="empty description")
    task_id = add_task(user_id, desc)
    if body.deadline:
        set_deadline(task_id, _to_utc_or_none(body.deadline, user_id))
    if body.reminder_at:
        set_reminder_at(task_id, _to_utc_or_none(body.reminder_at, user_id))
    return _decorate(get_task(task_id), _now_utc())


@app.post("/api/tasks/{task_id}/complete")
async def api_complete(
    task_id: int, user_id: int = Depends(current_user_id)
) -> dict:
    _require_own_task(user_id, task_id)
    result = complete_task(task_id)
    return result if result is not None else {"completed": False}


@app.post("/api/tasks/{task_id}/uncomplete")
async def api_uncomplete(
    task_id: int, user_id: int = Depends(current_user_id)
) -> dict:
    _require_own_task(user_id, task_id)
    return {"ok": mark_task_undone(task_id)}


@app.patch("/api/tasks/{task_id}")
async def api_patch_task(
    task_id: int,
    body: TaskPatch,
    user_id: int = Depends(current_user_id),
) -> dict:
    _require_own_task(user_id, task_id)
    if body.description is not None:
        update_task_description(task_id, body.description.strip())
    if body.important is not None:
        set_important(task_id, body.important)
    if body.clear_deadline:
        set_deadline(task_id, None)
    elif body.deadline:
        set_deadline(task_id, _to_utc_or_none(body.deadline, user_id))
    if body.clear_reminder:
        set_reminder_at(task_id, None)
    elif body.reminder_at:
        set_reminder_at(task_id, _to_utc_or_none(body.reminder_at, user_id))
    if body.clear_recurrence:
        set_recurrence(task_id, None)
    elif body.recurrence is not None:
        if body.recurrence not in RECURRENCES:
            raise HTTPException(status_code=422, detail="bad recurrence")
        set_recurrence(task_id, body.recurrence)
    if body.clear_notes:
        set_note(task_id, None)
    elif body.notes is not None:
        set_note(task_id, body.notes)
    return _decorate(get_task(task_id), _now_utc())


def _require_step(user_id: int, task_id: int, step_id: int) -> None:
    _require_own_task(user_id, task_id)
    if step_id not in {s["id"] for s in get_steps(task_id)}:
        raise HTTPException(status_code=404, detail="step not found")


@app.get("/api/tasks/{task_id}/steps")
async def api_steps(
    task_id: int, user_id: int = Depends(current_user_id)
) -> list[dict]:
    _require_own_task(user_id, task_id)
    return get_steps(task_id)


@app.post("/api/tasks/{task_id}/steps")
async def api_add_step(
    task_id: int,
    body: StepCreate,
    user_id: int = Depends(current_user_id),
) -> dict:
    _require_own_task(user_id, task_id)
    desc = body.description.strip()
    if not desc:
        raise HTTPException(status_code=422, detail="empty step")
    return {"id": add_step(task_id, desc), "description": desc,
            "completed": False}


@app.post("/api/tasks/{task_id}/steps/{step_id}/toggle")
async def api_toggle_step(
    task_id: int,
    step_id: int,
    body: StepToggle,
    user_id: int = Depends(current_user_id),
) -> dict:
    _require_step(user_id, task_id, step_id)
    return {"ok": mark_step_done(step_id, body.done)}


@app.delete("/api/tasks/{task_id}/steps/{step_id}")
async def api_delete_step(
    task_id: int,
    step_id: int,
    user_id: int = Depends(current_user_id),
) -> dict:
    _require_step(user_id, task_id, step_id)
    return {"ok": delete_step(step_id)}


@app.get("/api/myday")
async def api_myday(user_id: int = Depends(current_user_id)) -> list[dict]:
    tasks = get_myday(user_id, _today_local(user_id))
    now = _now_utc()
    return [_decorate(t, now) for t in tasks]


@app.post("/api/tasks/{task_id}/myday")
async def api_toggle_myday(
    task_id: int,
    body: MyDayToggle,
    user_id: int = Depends(current_user_id),
) -> dict:
    _require_own_task(user_id, task_id)
    if body.on:
        add_to_myday(task_id, _today_local(user_id))
    else:
        remove_from_myday(task_id)
    return _decorate(get_task(task_id), _now_utc())


@app.get("/api/lists")
async def api_lists(user_id: int = Depends(current_user_id)) -> list[dict]:
    return get_lists(user_id)


@app.post("/api/lists")
async def api_create_list(
    body: ListCreate, user_id: int = Depends(current_user_id)
) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="empty name")
    return {"id": create_list(user_id, name), "name": name}


# Раздача фронтенда Mini App. Монтируется ПОСЛЕ API-маршрутов, чтобы
# /api/* и /healthz имели приоритет; "/" → static/index.html.
app.mount("/", StaticFiles(directory="static", html=True), name="static")

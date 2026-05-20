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
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from database import (
    add_step,
    add_task,
    add_to_myday,
    assign_task_to_list,
    complete_task,
    create_list,
    db_ping,
    delete_list,
    delete_step,
    export_user_data,
    get_global_counts,
    get_important_tasks,
    get_lists,
    get_myday,
    get_planned,
    get_steps,
    get_steps_counts,
    get_task,
    get_tasks,
    get_tasks_by_list,
    get_timezone,
    get_user_stats,
    import_user_data,
    init_db,
    is_valid_recurrence,
    mark_step_done,
    mark_task_undone,
    move_task_down,
    move_task_up,
    remove_from_myday,
    rename_list,
    search_tasks,
    set_deadline,
    set_important,
    set_list_color,
    set_note,
    set_recurrence,
    set_reminder_at,
    set_timezone,
    snooze_reminder,
    update_task_description,
)
from logsetup import setup_logging
from tzutil import to_local, to_utc

setup_logging("webapp")
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


def _decorate(
    task: dict,
    now: str,
    counts: dict[int, dict[str, int]] | None = None,
) -> dict:
    """
    Декорирует задачу служебными полями для UI:
    - `overdue` — срок прошёл и задача активна.
    - `steps_done`/`steps_total` — счётчики подзадач (только если
      `counts` передан и задача в нём есть; иначе оба 0).
    """
    dl = task.get("deadline")
    task["overdue"] = bool(
        dl and not task["completed"] and dl < now
    )
    c = (counts or {}).get(task["id"], {"done": 0, "total": 0})
    task["steps_done"] = c["done"]
    task["steps_total"] = c["total"]
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


class ListPatch(BaseModel):
    name: str | None = None
    color: str | None = None


class MoveList(BaseModel):
    list_id: int | None = None


class Settings(BaseModel):
    timezone: str


class MyDayToggle(BaseModel):
    on: bool = True


class StepCreate(BaseModel):
    description: str


class StepToggle(BaseModel):
    done: bool = True


class Snooze(BaseModel):
    minutes: int


_STARTED_AT = time.monotonic()


@asynccontextmanager
async def _lifespan(_app: FastAPI):  # pragma: no cover
    init_db()
    yield


app = FastAPI(title="Reminder Mini App API", lifespan=_lifespan)


@app.get("/healthz")
async def healthz():
    """
    Расширенный healthcheck для внешнего мониторинга и `systemctl`:
    - `ok`: True только если БД отвечает (SELECT 1) — иначе HTTP 503;
    - `uptime_seconds`: с момента старта процесса (monotonic, не часы);
    - сводные счётчики из `get_global_counts` — видно, что данные есть.
    Эндпоинт без авторизации (initData не требуется) — чтобы
    балансировщик/Caddy/systemd-таймер могли пинговать его извне.
    """
    db_ok = db_ping()
    body: dict = {
        "ok": bool(db_ok),
        "db": "ok" if db_ok else "fail",
        "uptime_seconds": round(time.monotonic() - _STARTED_AT, 1),
    }
    if db_ok:
        try:
            body.update(get_global_counts())
        except Exception as e:   # очень редко, но всё-таки страхуемся
            logger.warning("healthz counts failed: %s", e)
    return JSONResponse(body, status_code=200 if db_ok else 503)


@app.get("/api/tasks")
async def api_tasks(
    user_id: int = Depends(current_user_id),
    list_id: int | None = None,
    completed: bool = False,
    search: str | None = None,
    sort: str | None = None,
) -> list[dict]:
    if search and search.strip():
        tasks = search_tasks(user_id, search)
    elif list_id is None:
        tasks = get_tasks(user_id, completed=completed, sort=sort)
    else:
        real = None if list_id == 0 else list_id
        tasks = get_tasks_by_list(user_id, real, completed=completed)
    now = _now_utc()
    counts = get_steps_counts(user_id)
    return [_decorate(t, now, counts) for t in tasks]


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
        if not is_valid_recurrence(body.recurrence):
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
    counts = get_steps_counts(user_id)
    return [_decorate(t, now, counts) for t in tasks]


@app.get("/api/planned")
async def api_planned(user_id: int = Depends(current_user_id)) -> list[dict]:
    now = _now_utc()
    counts = get_steps_counts(user_id)
    return [_decorate(t, now, counts) for t in get_planned(user_id)]


@app.get("/api/important")
async def api_important(
    user_id: int = Depends(current_user_id),
) -> list[dict]:
    now = _now_utc()
    counts = get_steps_counts(user_id)
    return [_decorate(t, now, counts) for t in get_important_tasks(user_id)]


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


@app.post("/api/tasks/{task_id}/snooze")
async def api_snooze(
    task_id: int,
    body: Snooze,
    user_id: int = Depends(current_user_id),
) -> dict:
    _require_own_task(user_id, task_id)
    if body.minutes <= 0:
        raise HTTPException(status_code=422, detail="minutes must be > 0")
    snooze_reminder(task_id, body.minutes)
    return _decorate(get_task(task_id), _now_utc())


@app.post("/api/tasks/{task_id}/move-up")
async def api_move_up(
    task_id: int, user_id: int = Depends(current_user_id)
) -> dict:
    """Меняет местами с предыдущим активным соседом того же списка."""
    _require_own_task(user_id, task_id)
    moved = move_task_up(task_id)
    return {"moved": moved}


@app.post("/api/tasks/{task_id}/move-down")
async def api_move_down(
    task_id: int, user_id: int = Depends(current_user_id)
) -> dict:
    """Меняет местами со следующим активным соседом того же списка."""
    _require_own_task(user_id, task_id)
    moved = move_task_down(task_id)
    return {"moved": moved}


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


def _require_own_list(user_id: int, list_id: int) -> None:
    if list_id not in {lst["id"] for lst in get_lists(user_id)}:
        raise HTTPException(status_code=404, detail="list not found")


@app.patch("/api/lists/{list_id}")
async def api_rename_list(
    list_id: int,
    body: ListPatch,
    user_id: int = Depends(current_user_id),
) -> dict:
    _require_own_list(user_id, list_id)
    if body.name is None and body.color is None:
        raise HTTPException(
            status_code=422, detail="nothing to update"
        )
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="empty name")
        rename_list(list_id, name)
    if body.color is not None:
        if not set_list_color(list_id, body.color):
            raise HTTPException(
                status_code=422,
                detail="bad color (expected '#RRGGBB')",
            )
    lst = next(
        (lst for lst in get_lists(user_id) if lst["id"] == list_id), None
    )
    return lst or {"id": list_id}


@app.delete("/api/lists/{list_id}")
async def api_delete_list(
    list_id: int, user_id: int = Depends(current_user_id)
) -> dict:
    _require_own_list(user_id, list_id)
    return {"ok": delete_list(list_id)}


@app.post("/api/tasks/{task_id}/list")
async def api_move_task(
    task_id: int,
    body: MoveList,
    user_id: int = Depends(current_user_id),
) -> dict:
    _require_own_task(user_id, task_id)
    target = body.list_id or None
    if target is not None:
        _require_own_list(user_id, target)
    assign_task_to_list(task_id, target)
    return _decorate(get_task(task_id), _now_utc())


@app.get("/api/stats")
async def api_stats(
    user_id: int = Depends(current_user_id),
) -> dict:
    """Краткая сводка для текущего пользователя (Phase 10.3)."""
    return get_user_stats(user_id)


@app.get("/api/settings")
async def api_get_settings(
    user_id: int = Depends(current_user_id),
) -> dict:
    return {"timezone": get_timezone(user_id)}


@app.put("/api/settings")
async def api_set_settings(
    body: Settings, user_id: int = Depends(current_user_id)
) -> dict:
    tz = body.timezone.strip()
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail="bad timezone") from None
    set_timezone(user_id, tz)
    return {"timezone": tz}


# --- Экспорт / импорт пользовательских данных (Фаза 10.2) ---

class ImportBody(BaseModel):
    payload: dict
    mode: str = "merge"


@app.get("/api/export")
async def api_export(
    user_id: int = Depends(current_user_id),
) -> dict:
    """Возвращает полный JSON-снимок данных пользователя для бэкапа."""
    return export_user_data(user_id)


@app.post("/api/import")
async def api_import(
    body: ImportBody, user_id: int = Depends(current_user_id),
) -> dict:
    """Импортирует JSON-снимок. 422 при невалидной схеме/режиме."""
    try:
        return import_user_data(user_id, body.payload, mode=body.mode)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


# Раздача фронтенда Mini App. Монтируется ПОСЛЕ API-маршрутов, чтобы
# /api/* и /healthz имели приоритет; "/" → static/index.html.
app.mount("/", StaticFiles(directory="static", html=True), name="static")

"""Фаза 8.1: тесты HTTP API Mini App (initData-авторизация + REST)."""
import hashlib
import hmac
import json
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

import config
import webapp
from webapp import app, validate_init_data

TEST_TOKEN = "123456:TEST-TOKEN"


def make_init_data(user_id: int = 42, token: str = TEST_TOKEN,
                    tamper: bool = False) -> str:
    user = json.dumps(
        {"id": user_id, "first_name": "T"}, separators=(",", ":")
    )
    pairs = {"auth_date": "1700000000", "query_id": "AAA", "user": user}
    dcs = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    pairs["hash"] = ("0" * len(h)) if tamper else h
    return urlencode(pairs)


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", TEST_TOKEN)


@pytest.fixture
def client():
    return TestClient(app)


def hdr(user_id: int = 42) -> dict:
    return {"X-Init-Data": make_init_data(user_id)}


# --- validate_init_data ---

def test_validate_ok():
    u = validate_init_data(make_init_data(7), TEST_TOKEN)
    assert u and u["id"] == 7


@pytest.mark.parametrize(
    "data, token",
    [
        ("", TEST_TOKEN),
        (make_init_data(tamper=True), TEST_TOKEN),
        (make_init_data(), "wrong-token"),
        ("auth_date=1&hash=deadbeef", TEST_TOKEN),  # нет user
        ("user=notjson&hash=x", TEST_TOKEN),        # нет валидной подписи
    ],
)
def test_validate_rejects(data, token):
    assert validate_init_data(data, token) is None


def test_validate_user_without_id(monkeypatch):
    # валидная подпись, но в user нет id
    pairs = {"auth_date": "1", "user": json.dumps({"first_name": "X"})}
    dcs = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(
        b"WebAppData", TEST_TOKEN.encode(), hashlib.sha256
    ).digest()
    pairs["hash"] = hmac.new(
        secret, dcs.encode(), hashlib.sha256
    ).hexdigest()
    assert validate_init_data(urlencode(pairs), TEST_TOKEN) is None


# --- авторизация эндпоинтов ---

def test_tasks_requires_auth(client):
    assert client.get("/api/tasks").status_code == 401
    r = client.get("/api/tasks", headers={"X-Init-Data": "bad"})
    assert r.status_code == 401


def test_healthz_returns_db_ok_and_counts(client):
    """С Фазы 10.3 /healthz пингует БД и отдаёт счётчики."""
    body = client.get("/healthz").json()
    assert body["ok"] is True
    assert body["db"] == "ok"
    assert "uptime_seconds" in body
    # На свежей тестовой БД задач/списков нет, но ключи присутствуют.
    for k in ("tasks_total", "tasks_active", "lists_total", "users"):
        assert k in body


# --- CRUD задач ---

def test_create_list_complete_flow(client):
    r = client.post(
        "/api/tasks", json={"description": "Купить хлеб"}, headers=hdr()
    )
    assert r.status_code == 200
    tid = r.json()["id"]

    lst = client.get("/api/tasks", headers=hdr()).json()
    assert [t["id"] for t in lst] == [tid]
    assert lst[0]["overdue"] is False

    assert client.post(
        f"/api/tasks/{tid}/complete", headers=hdr()
    ).json()["completed"] is True
    assert client.get("/api/tasks", headers=hdr()).json() == []
    done = client.get(
        "/api/tasks?completed=true", headers=hdr()
    ).json()
    assert [t["id"] for t in done] == [tid]

    assert client.post(
        f"/api/tasks/{tid}/uncomplete", headers=hdr()
    ).json() == {"ok": True}


def test_create_empty_description_422(client):
    r = client.post("/api/tasks", json={"description": "  "}, headers=hdr())
    assert r.status_code == 422


def test_overdue_flag_for_past_deadline(client):
    r = client.post(
        "/api/tasks",
        json={"description": "Просроч", "deadline": "2020-01-01 00:00"},
        headers=hdr(),
    )
    assert r.json()["overdue"] is True


def test_patch_important_and_description(client):
    tid = client.post(
        "/api/tasks", json={"description": "old"}, headers=hdr()
    ).json()["id"]
    r = client.patch(
        f"/api/tasks/{tid}",
        json={"important": True, "description": "new"},
        headers=hdr(),
    )
    body = r.json()
    assert body["important"] is True and body["description"] == "new"


def test_patch_clear_deadline(client):
    tid = client.post(
        "/api/tasks",
        json={"description": "x", "deadline": "2020-01-01 00:00"},
        headers=hdr(),
    ).json()["id"]
    r = client.patch(
        f"/api/tasks/{tid}", json={"clear_deadline": True}, headers=hdr()
    )
    assert r.json()["deadline"] is None
    assert r.json()["overdue"] is False


def test_ownership_enforced(client):
    tid = client.post(
        "/api/tasks", json={"description": "A's"}, headers=hdr(42)
    ).json()["id"]
    # другой пользователь не может трогать чужую задачу
    assert client.post(
        f"/api/tasks/{tid}/complete", headers=hdr(99)
    ).status_code == 404
    assert client.patch(
        f"/api/tasks/{tid}", json={"important": True}, headers=hdr(99)
    ).status_code == 404


def test_lists_endpoints(client):
    assert client.get("/api/lists", headers=hdr()).json() == []
    r = client.post(
        "/api/lists", json={"name": "Работа"}, headers=hdr()
    )
    assert r.status_code == 200 and r.json()["name"] == "Работа"
    names = [x["name"] for x in client.get(
        "/api/lists", headers=hdr()
    ).json()]
    assert names == ["Работа"]
    assert client.post(
        "/api/lists", json={"name": " "}, headers=hdr()
    ).status_code == 422


def test_tasks_by_list_filter(client):
    lid = client.post(
        "/api/lists", json={"name": "L"}, headers=hdr()
    ).json()["id"]
    client.post("/api/tasks", json={"description": "nolist"}, headers=hdr())
    # задач в списке нет
    assert client.get(
        f"/api/tasks?list_id={lid}", headers=hdr()
    ).json() == []
    # list_id=0 → задачи без списка
    assert len(client.get("/api/tasks?list_id=0", headers=hdr()).json()) == 1


def test_complete_nonexistent_returns_404(client):
    assert client.post(
        "/api/tasks/999999/complete", headers=hdr()
    ).status_code == 404


def test_validate_user_invalid_json():
    # валидная подпись, но user — невалидный JSON (ветка except)
    pairs = {"auth_date": "1", "user": "{not-json"}
    dcs = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(
        b"WebAppData", TEST_TOKEN.encode(), hashlib.sha256
    ).digest()
    pairs["hash"] = hmac.new(
        secret, dcs.encode(), hashlib.sha256
    ).hexdigest()
    assert validate_init_data(urlencode(pairs), TEST_TOKEN) is None


def test_to_utc_or_none_helper():
    assert webapp._to_utc_or_none(None, 1) is None
    assert webapp._to_utc_or_none("2026-05-18 15:00", 1) == (
        "2026-05-18 15:00:00"
    )


def test_patch_set_deadline_and_reminder(client):
    tid = client.post(
        "/api/tasks", json={"description": "p"}, headers=hdr()
    ).json()["id"]
    r = client.patch(
        f"/api/tasks/{tid}",
        json={"deadline": "2030-01-01 00:00",
              "reminder_at": "2030-01-02 09:00"},
        headers=hdr(),
    )
    body = r.json()
    assert body["deadline"] == "2030-01-01 00:00:00"
    assert body["reminder_at"] == "2030-01-02 09:00:00"
    assert body["overdue"] is False

    r2 = client.patch(
        f"/api/tasks/{tid}", json={"clear_reminder": True}, headers=hdr()
    )
    assert r2.json()["reminder_at"] is None


def test_frontend_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Мои задачи" in r.text
    assert "telegram-web-app.js" in r.text


def test_api_routes_take_priority_over_static(client):
    # mount "/" не должен перекрывать API: /api/* без авторизации = 401
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/healthz").status_code == 200


# --- Фаза 8.4: повторы + «Мой день» ---

def test_patch_recurrence_set_invalid_clear(client):
    tid = client.post(
        "/api/tasks", json={"description": "r"}, headers=hdr()
    ).json()["id"]
    ok = client.patch(
        f"/api/tasks/{tid}", json={"recurrence": "weekly"}, headers=hdr()
    )
    assert ok.json()["recurrence"] == "weekly"
    bad = client.patch(
        f"/api/tasks/{tid}", json={"recurrence": "hourly"}, headers=hdr()
    )
    assert bad.status_code == 422
    cl = client.patch(
        f"/api/tasks/{tid}", json={"clear_recurrence": True}, headers=hdr()
    )
    assert cl.json()["recurrence"] is None


def test_patch_recurrence_custom(client):
    tid = client.post(
        "/api/tasks", json={"description": "r"}, headers=hdr()
    ).json()["id"]
    e = client.patch(
        f"/api/tasks/{tid}", json={"recurrence": "every:3:d"}, headers=hdr()
    )
    assert e.json()["recurrence"] == "every:3:d"
    w = client.patch(
        f"/api/tasks/{tid}",
        json={"recurrence": "weekdays:MO,WE,FR"}, headers=hdr(),
    )
    assert w.json()["recurrence"] == "weekdays:MO,WE,FR"
    bad = client.patch(
        f"/api/tasks/{tid}", json={"recurrence": "every:0:d"}, headers=hdr()
    )
    assert bad.status_code == 422


def test_myday_toggle_and_list(client):
    assert client.get("/api/myday", headers=hdr()).json() == []
    tid = client.post(
        "/api/tasks", json={"description": "md"}, headers=hdr()
    ).json()["id"]
    on = client.post(
        f"/api/tasks/{tid}/myday", json={"on": True}, headers=hdr()
    )
    assert on.json()["myday_date"]
    ids = [t["id"] for t in client.get("/api/myday", headers=hdr()).json()]
    assert ids == [tid]
    off = client.post(
        f"/api/tasks/{tid}/myday", json={"on": False}, headers=hdr()
    )
    assert off.json()["myday_date"] is None
    assert client.get("/api/myday", headers=hdr()).json() == []


def test_myday_toggle_ownership(client):
    tid = client.post(
        "/api/tasks", json={"description": "x"}, headers=hdr(42)
    ).json()["id"]
    r = client.post(
        f"/api/tasks/{tid}/myday", json={"on": True}, headers=hdr(99)
    )
    assert r.status_code == 404


# --- Фаза 8.5: подзадачи + заметки ---

def test_notes_patch_set_and_clear(client):
    tid = client.post(
        "/api/tasks", json={"description": "n"}, headers=hdr()
    ).json()["id"]
    r = client.patch(
        f"/api/tasks/{tid}", json={"notes": "позвонить"}, headers=hdr()
    )
    assert r.json()["notes"] == "позвонить"
    r2 = client.patch(
        f"/api/tasks/{tid}", json={"clear_notes": True}, headers=hdr()
    )
    assert r2.json()["notes"] is None


def test_steps_crud(client):
    tid = client.post(
        "/api/tasks", json={"description": "p"}, headers=hdr()
    ).json()["id"]
    assert client.get(
        f"/api/tasks/{tid}/steps", headers=hdr()
    ).json() == []

    s = client.post(
        f"/api/tasks/{tid}/steps", json={"description": "шаг 1"},
        headers=hdr(),
    ).json()
    assert s["description"] == "шаг 1" and s["completed"] is False
    sid = s["id"]
    got = client.get(f"/api/tasks/{tid}/steps", headers=hdr()).json()
    assert [x["id"] for x in got] == [sid]

    assert client.post(
        f"/api/tasks/{tid}/steps", json={"description": " "}, headers=hdr()
    ).status_code == 422

    tg = client.post(
        f"/api/tasks/{tid}/steps/{sid}/toggle",
        json={"done": True}, headers=hdr(),
    )
    assert tg.json() == {"ok": True}
    assert client.get(
        f"/api/tasks/{tid}/steps", headers=hdr()
    ).json()[0]["completed"] is True

    d = client.request(
        "DELETE", f"/api/tasks/{tid}/steps/{sid}", headers=hdr()
    )
    assert d.json() == {"ok": True}
    assert client.get(f"/api/tasks/{tid}/steps", headers=hdr()).json() == []


def test_steps_ownership_and_wrong_task(client):
    tid_a = client.post(
        "/api/tasks", json={"description": "A"}, headers=hdr(42)
    ).json()["id"]
    sid = client.post(
        f"/api/tasks/{tid_a}/steps", json={"description": "s"},
        headers=hdr(42),
    ).json()["id"]
    # чужой пользователь
    assert client.get(
        f"/api/tasks/{tid_a}/steps", headers=hdr(99)
    ).status_code == 404
    assert client.post(
        f"/api/tasks/{tid_a}/steps", json={"description": "x"},
        headers=hdr(99),
    ).status_code == 404
    # шаг не принадлежит другой задаче того же юзера
    tid_b = client.post(
        "/api/tasks", json={"description": "B"}, headers=hdr(42)
    ).json()["id"]
    assert client.post(
        f"/api/tasks/{tid_b}/steps/{sid}/toggle",
        json={"done": True}, headers=hdr(42),
    ).status_code == 404
    assert client.request(
        "DELETE", f"/api/tasks/{tid_b}/steps/{sid}", headers=hdr(42)
    ).status_code == 404


# --- Фаза 8.6: поиск + сортировки ---

def test_tasks_search(client):
    client.post(
        "/api/tasks", json={"description": "купить хлеб"}, headers=hdr()
    )
    client.post(
        "/api/tasks", json={"description": "помыть машину"}, headers=hdr()
    )
    res = client.get("/api/tasks?search=хлеб", headers=hdr()).json()
    assert [t["description"] for t in res] == ["купить хлеб"]
    assert client.get("/api/tasks?search=ничего", headers=hdr()).json() == []


def test_tasks_sort_important_first(client):
    a = client.post(
        "/api/tasks", json={"description": "A"}, headers=hdr()
    ).json()["id"]
    b = client.post(
        "/api/tasks", json={"description": "B"}, headers=hdr()
    ).json()["id"]
    client.patch(
        f"/api/tasks/{b}", json={"important": True}, headers=hdr()
    )
    ids = [
        t["id"]
        for t in client.get(
            "/api/tasks?sort=important", headers=hdr()
        ).json()
    ]
    assert ids == [b, a]


# --- Фаза 8.7: списки (rename/delete/move) + часовой пояс ---

def test_list_rename_delete_and_ownership(client):
    lid = client.post(
        "/api/lists", json={"name": "L"}, headers=hdr(42)
    ).json()["id"]
    r = client.patch(
        f"/api/lists/{lid}", json={"name": "L2"}, headers=hdr(42)
    )
    # С Фазы 9.5 эндпоинт возвращает весь dict списка (с color и др.),
    # поэтому проверяем только нужные поля.
    body = r.json()
    assert body["id"] == lid and body["name"] == "L2"
    assert [x["name"] for x in client.get(
        "/api/lists", headers=hdr(42)
    ).json()] == ["L2"]
    # пустое имя
    assert client.patch(
        f"/api/lists/{lid}", json={"name": " "}, headers=hdr(42)
    ).status_code == 422
    # чужой
    assert client.patch(
        f"/api/lists/{lid}", json={"name": "x"}, headers=hdr(99)
    ).status_code == 404
    assert client.request(
        "DELETE", f"/api/lists/{lid}", headers=hdr(99)
    ).status_code == 404
    assert client.request(
        "DELETE", f"/api/lists/{lid}", headers=hdr(42)
    ).json() == {"ok": True}
    assert client.get("/api/lists", headers=hdr(42)).json() == []


def test_move_task_between_lists(client):
    lid = client.post(
        "/api/lists", json={"name": "Work"}, headers=hdr()
    ).json()["id"]
    tid = client.post(
        "/api/tasks", json={"description": "t"}, headers=hdr()
    ).json()["id"]
    r = client.post(
        f"/api/tasks/{tid}/list", json={"list_id": lid}, headers=hdr()
    )
    assert r.json()["list_id"] == lid
    assert [t["id"] for t in client.get(
        f"/api/tasks?list_id={lid}", headers=hdr()
    ).json()] == [tid]
    # обратно «без списка»
    back = client.post(
        f"/api/tasks/{tid}/list", json={"list_id": 0}, headers=hdr()
    )
    assert back.json()["list_id"] is None
    # чужой список → 404
    assert client.post(
        f"/api/tasks/{tid}/list", json={"list_id": 999999}, headers=hdr()
    ).status_code == 404


def test_settings_timezone(client):
    assert client.get("/api/settings", headers=hdr()).json() == {
        "timezone": "UTC"
    }
    ok = client.put(
        "/api/settings", json={"timezone": "Europe/Moscow"}, headers=hdr()
    )
    assert ok.json() == {"timezone": "Europe/Moscow"}
    assert client.get("/api/settings", headers=hdr()).json()[
        "timezone"
    ] == "Europe/Moscow"
    assert client.put(
        "/api/settings", json={"timezone": "Mars/Olympus"}, headers=hdr()
    ).status_code == 422


# --- Фаза 9.2: smart-views (Planned, Important) ---

def test_db_get_planned_filters_and_orders():
    from database import (
        add_task,
        get_important_tasks,
        get_planned,
        mark_task_done,
        set_deadline,
        set_important,
        set_reminder_at,
    )
    # 42 — пользователь под тест; пара задач разной формы
    plain = add_task(42, "plain")                   # без дедлайна/напом. → нет
    early = add_task(42, "early")
    set_deadline(early, "2026-05-19 09:00:00")
    late = add_task(42, "late")
    set_deadline(late, "2026-05-20 09:00:00")
    rem = add_task(42, "reminder-only")
    set_reminder_at(rem, "2026-05-19 18:00:00")     # дедлайна нет, напом. есть
    done = add_task(42, "done")
    set_deadline(done, "2026-05-19 10:00:00")
    mark_task_done(done)
    other = add_task(99, "other")                   # чужой
    set_deadline(other, "2026-05-19 09:00:00")
    assert plain and other  # silence

    ids = [t["id"] for t in get_planned(42)]
    # сначала по дедлайну (early, late), потом напоминание-only (rem);
    # без дедлайна/напом. (plain) и выполненная (done), и чужие — не входят
    assert ids == [early, late, rem]

    # important
    set_important(late, True)
    assert [t["id"] for t in get_important_tasks(42)] == [late]


def test_api_planned_and_important(client):
    a = client.post("/api/tasks", json={"description": "a"}, headers=hdr()).json()["id"]
    b = client.post("/api/tasks", json={"description": "b"}, headers=hdr()).json()["id"]
    # a: дедлайн; b: только напоминание + важная
    client.patch(f"/api/tasks/{a}",
                 json={"deadline": "2026-05-19 09:00"}, headers=hdr())
    client.patch(f"/api/tasks/{b}",
                 json={"reminder_at": "2026-05-19 10:00", "important": True},
                 headers=hdr())
    planned = [t["id"] for t in client.get(
        "/api/planned", headers=hdr()).json()]
    assert planned == [a, b]
    imp = [t["id"] for t in client.get(
        "/api/important", headers=hdr()).json()]
    assert imp == [b]
    # авторизация требуется
    assert client.get("/api/planned").status_code == 401
    assert client.get("/api/important").status_code == 401


# --- Фаза 9.3: snooze ---

def test_db_snooze_reminder_sets_future_and_resets_sent():
    from datetime import UTC, datetime

    from database import (
        add_task,
        get_task,
        mark_reminder_sent,
        set_reminder_at,
        snooze_reminder,
    )
    tid = add_task(1, "t")
    set_reminder_at(tid, "2020-01-01 00:00:00")
    mark_reminder_sent(tid)
    assert get_task(tid)["reminder_sent"] == 1

    assert snooze_reminder(tid, 30) is True
    now = datetime.now(UTC).replace(tzinfo=None)
    new = datetime.strptime(get_task(tid)["reminder_at"], "%Y-%m-%d %H:%M:%S")
    delta_min = (new - now).total_seconds() / 60
    assert 29 <= delta_min <= 31  # +30 минут от текущего UTC
    assert get_task(tid)["reminder_sent"] == 0   # сброшен

    # некорректные параметры
    assert snooze_reminder(tid, 0) is False
    assert snooze_reminder(tid, -5) is False
    assert snooze_reminder(999999, 10) is False


def test_api_snooze(client):
    tid = client.post(
        "/api/tasks", json={"description": "x"}, headers=hdr()
    ).json()["id"]
    r = client.post(
        f"/api/tasks/{tid}/snooze", json={"minutes": 15}, headers=hdr()
    )
    assert r.status_code == 200 and r.json()["reminder_at"]
    bad = client.post(
        f"/api/tasks/{tid}/snooze", json={"minutes": 0}, headers=hdr()
    )
    assert bad.status_code == 422
    # чужая задача
    assert client.post(
        f"/api/tasks/{tid}/snooze", json={"minutes": 5}, headers=hdr(99)
    ).status_code == 404


# --- Фаза 9.4: ручной порядок ---

def test_db_add_task_sets_order_index_max_plus_one():
    """Каждая новая задача получает order_index = max(прошлых)+1 для user."""
    from database import add_task, get_task
    a = add_task(1, "a")
    b = add_task(1, "b")
    c = add_task(1, "c")
    assert get_task(a)["order_index"] < get_task(b)["order_index"]
    assert get_task(b)["order_index"] < get_task(c)["order_index"]
    # У другого пользователя — независимая последовательность.
    x = add_task(2, "x")
    assert get_task(x)["order_index"] == 1


def test_db_get_tasks_default_orders_by_manual():
    """get_tasks(sort=None) сортирует по order_index, не по id/created."""
    from database import add_task, get_tasks, move_task_up
    a = add_task(7, "a")
    b = add_task(7, "b")
    c = add_task(7, "c")
    # начало: a, b, c
    ids = [t["id"] for t in get_tasks(7)]
    assert ids == [a, b, c]
    # двигаем c вверх дважды → c, a, b
    move_task_up(c)
    move_task_up(c)
    ids2 = [t["id"] for t in get_tasks(7)]
    assert ids2 == [c, a, b]


def test_db_move_task_up_down_swap():
    from database import (
        add_task,
        get_tasks,
        move_task_down,
        move_task_up,
    )
    a = add_task(3, "a")
    b = add_task(3, "b")
    c = add_task(3, "c")
    assert [t["id"] for t in get_tasks(3)] == [a, b, c]
    assert move_task_down(a) is True   # b, a, c
    assert [t["id"] for t in get_tasks(3)] == [b, a, c]
    assert move_task_up(c) is True     # b, c, a
    assert [t["id"] for t in get_tasks(3)] == [b, c, a]
    # крайние — двигать нечего
    assert move_task_up(b) is False
    assert move_task_down(a) is False


def test_db_move_task_only_swaps_same_user_and_list():
    """Сосед — тот же user, тот же list_id (включая NULL=NULL)."""
    from database import (
        add_task,
        assign_task_to_list,
        create_list,
        get_tasks,
        get_tasks_by_list,
        move_task_down,
        move_task_up,
    )
    lid = create_list(4, "L")
    a = add_task(4, "a")           # без списка
    b = add_task(4, "b")           # без списка
    c = add_task(4, "c")
    d = add_task(4, "d")
    assign_task_to_list(c, lid)    # в списке L
    assign_task_to_list(d, lid)    # в том же списке
    foreign = add_task(99, "f")    # чужой пользователь, выше по индексу
    # move_down(a): сосед — b (без списка), НЕ c (другой список) и НЕ foreign.
    assert move_task_down(a) is True
    assert [t["id"] for t in get_tasks_by_list(4, None)] == [b, a]
    # внутри списка L: c, d → move_up(d) → d, c
    assert move_task_up(d) is True
    assert [t["id"] for t in get_tasks_by_list(4, lid)] == [d, c]
    # foreign не сдвинулся
    assert [t["id"] for t in get_tasks(99)] == [foreign]


def test_db_move_task_skips_completed_neighbor():
    """Выполненные задачи — не соседи (они скрыты в активном списке)."""
    from database import add_task, complete_task, get_tasks, move_task_down
    a = add_task(5, "a")
    b = add_task(5, "b")
    c = add_task(5, "c")
    complete_task(b)                # b теперь выполнен → пропускаем
    assert [t["id"] for t in get_tasks(5)] == [a, c]
    assert move_task_down(a) is True
    assert [t["id"] for t in get_tasks(5)] == [c, a]


def test_db_move_task_invalid_returns_false():
    from database import add_task, complete_task, move_task_down, move_task_up
    a = add_task(6, "a")
    complete_task(a)
    assert move_task_up(a) is False     # сама выполнена
    assert move_task_down(a) is False
    assert move_task_up(999999) is False  # нет такой
    assert move_task_down(999999) is False


def test_api_move_up_down(client):
    a = client.post(
        "/api/tasks", json={"description": "a"}, headers=hdr()
    ).json()["id"]
    b = client.post(
        "/api/tasks", json={"description": "b"}, headers=hdr()
    ).json()["id"]
    # b — последняя, поднимем её
    r = client.post(f"/api/tasks/{b}/move-up", headers=hdr())
    assert r.status_code == 200 and r.json()["moved"] is True
    ids = [t["id"] for t in client.get("/api/tasks", headers=hdr()).json()]
    assert ids == [b, a]
    # b уже первая — move-up = False
    r2 = client.post(f"/api/tasks/{b}/move-up", headers=hdr())
    assert r2.status_code == 200 and r2.json()["moved"] is False
    # и снова вниз
    r3 = client.post(f"/api/tasks/{b}/move-down", headers=hdr())
    assert r3.status_code == 200 and r3.json()["moved"] is True
    ids2 = [t["id"] for t in client.get("/api/tasks", headers=hdr()).json()]
    assert ids2 == [a, b]


def test_api_move_others_task_404(client):
    tid = client.post(
        "/api/tasks", json={"description": "x"}, headers=hdr()
    ).json()["id"]
    assert client.post(
        f"/api/tasks/{tid}/move-up", headers=hdr(99)
    ).status_code == 404
    assert client.post(
        f"/api/tasks/{tid}/move-down", headers=hdr(99)
    ).status_code == 404


# --- Фаза 9.5: счётчик подзадач + цвет списка ---

def test_db_get_steps_counts_aggregates_per_task():
    """Один SQL — done/total для всех задач пользователя; без подзадач — нет."""
    from database import add_step, add_task, get_steps_counts, mark_step_done
    a = add_task(11, "a")
    b = add_task(11, "b")
    add_task(11, "c")               # без подзадач — отсутствует в результате
    s1 = add_step(a, "a1")
    add_step(a, "a2")
    add_step(b, "b1")
    mark_step_done(s1, True)
    counts = get_steps_counts(11)
    assert counts == {a: {"done": 1, "total": 2}, b: {"done": 0, "total": 1}}
    # пользователь без подзадач — пустой dict
    assert get_steps_counts(999) == {}


def test_api_tasks_includes_steps_counts(client):
    tid = client.post(
        "/api/tasks", json={"description": "x"}, headers=hdr()
    ).json()["id"]
    client.post(
        f"/api/tasks/{tid}/steps", json={"description": "s1"}, headers=hdr()
    )
    client.post(
        f"/api/tasks/{tid}/steps", json={"description": "s2"}, headers=hdr()
    )
    t = next(t for t in client.get("/api/tasks", headers=hdr()).json()
             if t["id"] == tid)
    assert t["steps_total"] == 2 and t["steps_done"] == 0
    # myday/planned/important тоже декорируют (если попадают)
    client.post(
        f"/api/tasks/{tid}/myday", json={"on": True}, headers=hdr()
    )
    t2 = next(t for t in client.get("/api/myday", headers=hdr()).json()
              if t["id"] == tid)
    assert t2["steps_total"] == 2


def test_db_is_valid_color_and_set_list_color():
    from database import (
        create_list,
        get_lists,
        is_valid_color,
        set_list_color,
    )
    assert is_valid_color("#FFAA00") is True
    assert is_valid_color("#ffaa00") is True
    assert is_valid_color("#fff") is False    # короткий
    assert is_valid_color("red") is False
    assert is_valid_color(None) is False
    assert is_valid_color("") is False
    lid = create_list(50, "L")
    # дефолт — синий
    assert get_lists(50)[0]["color"] == "#0088CC"
    assert set_list_color(lid, "#10b981") is True
    assert get_lists(50)[0]["color"] == "#10b981"
    # невалидный
    assert set_list_color(lid, "no") is False
    assert get_lists(50)[0]["color"] == "#10b981"  # не изменился
    # нет такого списка
    assert set_list_color(999999, "#FFFFFF") is False


def test_api_list_patch_color(client):
    lid = client.post(
        "/api/lists", json={"name": "L"}, headers=hdr()
    ).json()["id"]
    # цвет
    r = client.patch(
        f"/api/lists/{lid}", json={"color": "#FFAA00"}, headers=hdr()
    )
    assert r.status_code == 200 and r.json()["color"] == "#FFAA00"
    # имя+цвет одной патчой
    r2 = client.patch(
        f"/api/lists/{lid}",
        json={"name": "L2", "color": "#10B981"}, headers=hdr(),
    )
    assert r2.json()["name"] == "L2" and r2.json()["color"] == "#10B981"
    # пустое тело
    assert client.patch(
        f"/api/lists/{lid}", json={}, headers=hdr()
    ).status_code == 422
    # битый цвет
    assert client.patch(
        f"/api/lists/{lid}", json={"color": "bad"}, headers=hdr()
    ).status_code == 422
    # чужой
    assert client.patch(
        f"/api/lists/{lid}", json={"color": "#000000"}, headers=hdr(99)
    ).status_code == 404


# --- Этап 38: стабильность (WAL + busy_timeout) ---

# --- Фаза 10.2: экспорт / импорт ---

def test_db_export_user_data_roundtrip():
    """
    Полный снимок: списки, задачи, подзадачи, настройки. Затем тот же
    payload импортируется ДРУГИМ пользователем и даёт совпадающие данные.
    """
    from database import (
        add_step,
        add_task,
        assign_task_to_list,
        create_list,
        export_user_data,
        get_lists,
        get_steps,
        get_tasks,
        get_timezone,
        import_user_data,
        mark_step_done,
        set_important,
        set_list_color,
        set_recurrence,
        set_timezone,
    )
    lid = create_list(100, "Work")
    set_list_color(lid, "#ff8800")
    a = add_task(100, "alpha")
    assign_task_to_list(a, lid)
    set_important(a, True)
    set_recurrence(a, "daily")
    add_task(100, "beta")           # без списка
    s1 = add_step(a, "step1")
    add_step(a, "step2")
    mark_step_done(s1, True)
    set_timezone(100, "Europe/Moscow")

    payload = export_user_data(100)
    assert payload["version"] == 1
    assert payload["user"]["id"] == 100
    assert payload["user"]["timezone"] == "Europe/Moscow"
    assert {x["name"] for x in payload["lists"]} == {"Work"}
    assert payload["lists"][0]["color"] == "#ff8800"
    names = [t["description"] for t in payload["tasks"]]
    assert names == ["alpha", "beta"]
    alpha = payload["tasks"][0]
    assert alpha["important"] is True
    assert alpha["recurrence"] == "daily"
    assert alpha["list_name"] == "Work"
    assert len(alpha["steps"]) == 2
    assert alpha["steps"][0]["completed"] is True
    assert payload["tasks"][1]["list_name"] is None

    # Импортируем тому же payload'у — но другому user_id, чтобы не
    # путаться. Должен пересоздать всё в полном объёме.
    counts = import_user_data(200, payload, mode="merge")
    # С Phase 11.2 счётчик включает notes (в этом тесте — 0).
    assert counts == {"lists": 1, "tasks": 2, "steps": 2, "notes": 0}
    assert {x["name"] for x in get_lists(200)} == {"Work"}
    new_alpha = next(t for t in get_tasks(200) if t["description"] == "alpha")
    assert new_alpha["important"] is True
    assert new_alpha["recurrence"] == "daily"
    assert len(get_steps(new_alpha["id"])) == 2
    assert get_timezone(200) == "Europe/Moscow"


def test_db_import_merge_skips_existing_lists_by_name():
    """В merge-режиме список с тем же именем не дублируется."""
    from database import (
        create_list,
        export_user_data,
        get_lists,
        import_user_data,
    )
    create_list(101, "Home")
    payload = export_user_data(101)
    # Импортируем в того же пользователя — Home уже есть.
    counts = import_user_data(101, payload, mode="merge")
    assert counts["lists"] == 0
    assert [x["name"] for x in get_lists(101)] == ["Home"]


def test_db_import_replace_wipes_then_imports():
    from database import (
        add_task,
        create_list,
        export_user_data,
        get_lists,
        get_tasks,
        import_user_data,
    )
    create_list(102, "Old")
    add_task(102, "to-keep-from-payload")
    payload = export_user_data(102)
    # Загрязняем данные, потом replace должен их выкинуть.
    create_list(102, "Garbage")
    add_task(102, "garbage")
    counts = import_user_data(102, payload, mode="replace")
    assert counts["tasks"] == 1 and counts["lists"] == 1
    assert [x["name"] for x in get_lists(102)] == ["Old"]
    assert [t["description"] for t in get_tasks(102)] == ["to-keep-from-payload"]


def test_db_import_skips_malformed_entries_silently():
    """
    Дефенсивные пути: пустые имена/описания, не-dict в `tasks`, кривой
    цвет — пропускаются без падения; статистика считает только успешно
    добавленные строки.
    """
    from database import get_lists, get_steps, get_tasks, import_user_data
    payload = {
        "version": 1,
        "lists": [
            {"name": "", "color": "#000000"},          # пустое имя
            {"name": "  ", "color": "#FFFFFF"},        # whitespace
            {"name": "Real", "color": "not-a-color"},  # bad color → дефолт
        ],
        "tasks": [
            "not a dict",
            {"description": ""},                       # пустое описание
            {"description": "  "},
            {"description": "ok", "list_name": "Real",
             "steps": [{"description": ""}, {"description": "s1"}]},
        ],
    }
    counts = import_user_data(104, payload, mode="merge")
    assert counts == {"lists": 1, "tasks": 1, "steps": 1, "notes": 0}
    lists = get_lists(104)
    assert [x["name"] for x in lists] == ["Real"]
    assert lists[0]["color"] == "#0088CC"   # fallback после bad color
    tasks = get_tasks(104)
    assert [t["description"] for t in tasks] == ["ok"]
    assert [s["description"] for s in get_steps(tasks[0]["id"])] == ["s1"]


def test_db_import_rolls_back_on_db_error(monkeypatch):
    """
    Симулируем ошибку в середине импорта — транзакция должна
    откатиться, частичных данных не остаётся.
    """
    import sqlite3

    import database
    from database import (
        create_list,
        get_lists,
        get_tasks,
        import_user_data,
    )
    create_list(105, "Pre-existing")
    payload = {
        "version": 1,
        "lists": [{"name": "New"}],
        "tasks": [{"description": "ok"}, {"description": "boom"}],
    }
    real_conn = database.get_connection

    class _CursorProxy:
        def __init__(self, c):
            self._c = c
            self._n = 0

        def execute(self, sql, *a, **kw):
            if "INSERT INTO tasks" in sql:
                self._n += 1
                if self._n == 2:
                    raise sqlite3.OperationalError("simulated")
            return self._c.execute(sql, *a, **kw)
        def fetchone(self): return self._c.fetchone()
        def fetchall(self): return self._c.fetchall()
        @property
        def lastrowid(self): return self._c.lastrowid
        @property
        def rowcount(self): return self._c.rowcount

    class _ConnProxy:
        def __init__(self, c): self._c = c
        def cursor(self): return _CursorProxy(self._c.cursor())
        def commit(self): return self._c.commit()
        def rollback(self): return self._c.rollback()
        def close(self): return self._c.close()
        def execute(self, *a, **kw): return self._c.execute(*a, **kw)

    monkeypatch.setattr(
        database, "get_connection", lambda: _ConnProxy(real_conn())
    )
    try:
        import_user_data(105, payload, mode="merge")
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("expected the simulated error to propagate")
    monkeypatch.setattr(database, "get_connection", real_conn)
    # Должно остаться только то, что было до импорта (rollback сработал).
    assert [x["name"] for x in get_lists(105)] == ["Pre-existing"]
    assert get_tasks(105) == []


def test_db_import_rejects_bad_payload():
    from database import import_user_data
    for bad in ("not a dict", 5, None,
                {}, {"version": 999, "lists": [], "tasks": []},
                {"version": 1, "lists": [], "tasks": "no"},
                {"version": 1, "lists": "no", "tasks": []}):
        try:
            import_user_data(103, bad, mode="merge")
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")
    # Невалидный режим.
    valid = {"version": 1, "lists": [], "tasks": []}
    try:
        import_user_data(103, valid, mode="weird")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for bad mode")


def test_api_export_then_import(client):
    # Создаём данные у user 42.
    lid = client.post(
        "/api/lists", json={"name": "Travel"}, headers=hdr()
    ).json()["id"]
    client.patch(f"/api/lists/{lid}", json={"color": "#10B981"}, headers=hdr())
    tid = client.post(
        "/api/tasks", json={"description": "pack"}, headers=hdr()
    ).json()["id"]
    client.post(f"/api/tasks/{tid}/list",
                json={"list_id": lid}, headers=hdr())
    client.post(f"/api/tasks/{tid}/steps",
                json={"description": "passport"}, headers=hdr())

    exp = client.get("/api/export", headers=hdr()).json()
    assert exp["version"] == 1 and len(exp["tasks"]) == 1
    assert exp["tasks"][0]["list_name"] == "Travel"
    assert exp["tasks"][0]["steps"][0]["description"] == "passport"

    # Импортируем тот же payload другому юзеру.
    r = client.post(
        "/api/import",
        json={"payload": exp, "mode": "merge"},
        headers=hdr(77),
    )
    assert r.status_code == 200
    new_tasks = client.get("/api/tasks", headers=hdr(77)).json()
    assert [t["description"] for t in new_tasks] == ["pack"]
    assert [x["name"] for x in client.get(
        "/api/lists", headers=hdr(77)).json()] == ["Travel"]
    # Битый payload → 422
    bad = client.post(
        "/api/import", json={"payload": {"version": 999}}, headers=hdr(77)
    )
    assert bad.status_code == 422


# --- Фаза 10.3: здоровье / статистика / логи ---

def test_db_ping_ok():
    from database import db_ping
    assert db_ping() is True


def test_db_ping_returns_false_on_error(monkeypatch):
    """Если соединение бросает sqlite3.Error — db_ping ловит и → False."""
    import sqlite3

    import database
    def bad():
        raise sqlite3.OperationalError("simulated")
    monkeypatch.setattr(database, "get_connection", bad)
    assert database.db_ping() is False


def test_db_get_global_counts():
    from database import add_task, create_list, get_global_counts
    create_list(300, "X")
    add_task(300, "t1")
    add_task(301, "t2")        # другой пользователь
    counts = get_global_counts()
    assert counts["tasks_total"] >= 2
    assert counts["tasks_active"] >= 2
    assert counts["lists_total"] >= 1
    assert counts["users"] >= 2


def test_db_get_user_stats():
    from database import (
        add_step,
        add_task,
        complete_task,
        create_list,
        get_user_stats,
        set_important,
    )
    a = add_task(310, "a")
    b = add_task(310, "b")
    set_important(b, True)
    create_list(310, "L")
    add_step(a, "s1")
    add_step(a, "s2")
    complete_task(a)         # после complete: a выполнен, осталась b
    s = get_user_stats(310)
    # b — активна, a — выполнена; b важная.
    assert s["active"] == 1
    assert s["completed"] == 1
    assert s["important"] == 1
    assert s["lists"] == 1
    # steps только у `a` (теперь выполненной задачи) — но steps связаны с
    # задачей по task_id, без фильтра по completed; считаем только незакрытые.
    assert s["steps_open"] == 2
    assert s["oldest_open_at"] is not None


def test_api_stats(client):
    body = client.get("/api/stats", headers=hdr()).json()
    for k in ("active", "completed", "lists", "important",
              "steps_open", "oldest_open_at"):
        assert k in body
    # без авторизации — 401
    assert client.get("/api/stats").status_code == 401


def test_healthz_returns_503_when_db_down(client, monkeypatch):
    """Если db_ping вернул False — endpoint отдаёт HTTP 503."""
    import webapp
    monkeypatch.setattr(webapp, "db_ping", lambda: False)
    r = client.get("/healthz")
    assert r.status_code == 503
    body = r.json()
    assert body["ok"] is False
    assert body["db"] == "fail"


def test_healthz_survives_counts_failure(client, monkeypatch, caplog):
    """Если db_ping OK, но get_global_counts кинул — endpoint всё равно 200."""
    import webapp

    def boom():
        raise RuntimeError("simulated counts crash")
    monkeypatch.setattr(webapp, "get_global_counts", boom)
    with caplog.at_level("WARNING"):
        r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert any("healthz counts failed" in m for m in caplog.messages)


def test_logsetup_idempotent_and_quiets_noisy(monkeypatch):
    """
    setup_logging при повторном вызове не дублирует хендлеры; шумные
    логгеры подняты до WARNING (защита от утечки токена через httpx).
    """
    import logging as logging_mod

    import logsetup
    root = logging_mod.getLogger()
    # Сбросим маркер и хендлеры, чтобы протестировать с нуля.
    monkeypatch.setattr(root, "_bot_reminder_configured", False, raising=False)
    saved = list(root.handlers)
    root.handlers.clear()
    try:
        logsetup.setup_logging("test_app")
        first = len(root.handlers)
        logsetup.setup_logging("test_app")    # idempotency
        assert len(root.handlers) == first
        for name in ("httpx", "httpcore", "apscheduler", "telegram"):
            assert logging_mod.getLogger(name).level == logging_mod.WARNING
    finally:
        root.handlers[:] = saved


def test_logsetup_file_handler_when_log_dir_set(tmp_path, monkeypatch):
    """С LOG_DIR=<tmp_path> добавляется RotatingFileHandler с правильным путём."""
    import logging as logging_mod
    import logging.handlers as lh

    import logsetup
    root = logging_mod.getLogger()
    monkeypatch.setattr(root, "_bot_reminder_configured", False, raising=False)
    saved = list(root.handlers)
    root.handlers.clear()
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    try:
        logsetup.setup_logging("phase103")
        file_hs = [h for h in root.handlers
                   if isinstance(h, lh.RotatingFileHandler)]
        assert file_hs, "ожидался RotatingFileHandler"
        # Файл создаётся при первой записи, но имя должно соответствовать.
        assert "phase103.log" in file_hs[0].baseFilename
    finally:
        root.handlers[:] = saved


def test_logsetup_file_handler_failure_is_soft(tmp_path, monkeypatch):
    """Если LOG_DIR на запись недоступен — продолжаем без файла, не падаем."""
    import logging as logging_mod

    import logsetup
    root = logging_mod.getLogger()
    monkeypatch.setattr(root, "_bot_reminder_configured", False, raising=False)
    saved = list(root.handlers)
    root.handlers.clear()

    def bad_mkdir(self, *a, **kw):
        raise OSError("permission denied (simulated)")

    monkeypatch.setattr("pathlib.Path.mkdir", bad_mkdir)
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "blocked"))
    try:
        logsetup.setup_logging("phase103")   # не должно падать
        # stdout-хендлер всё равно должен быть добавлен.
        assert root.handlers, "ожидался хотя бы один хендлер"
    finally:
        root.handlers[:] = saved


def test_db_update_task_description_missing_returns_false():
    """Phase 11.1: контракт сохраняется и без чат-команд."""
    from database import update_task_description
    assert update_task_description(999999, "x") is False


def test_db_mark_task_undone_missing_returns_false():
    from database import mark_task_undone
    assert mark_task_undone(999999) is False


def test_db_connection_uses_wal_and_busy_timeout():
    """
    Без WAL писатель блокирует всех читателей — на VPS это проявлялось
    как «залипшая» менюшка в Mini App, когда scheduler и webapp
    одновременно касаются БД. busy_timeout=5000 страхует от
    мгновенного OperationalError.
    """
    from database import get_connection
    conn = get_connection()
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        bt = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal", f"journal_mode is {mode!r}, expected wal"
    assert bt == 5000, f"busy_timeout is {bt}, expected 5000"
    assert fk == 1, "foreign_keys must remain ON"


# --- Фаза 10.5: курируемый список часовых поясов ---

def test_list_common_timezones_includes_moscow_and_utc():
    """Базовая проверка содержимого: ключевые зоны на месте, структура валидна."""
    from tzutil import list_common_timezones
    zones = list_common_timezones()
    by_tz = {z["tz"]: z for z in zones}
    # Проверочные зоны в каждой группе:
    assert "Europe/Moscow" in by_tz
    assert by_tz["Europe/Moscow"]["group"] == "Россия"
    assert by_tz["Europe/Moscow"]["label"] == "Москва"
    assert "UTC" in by_tz
    assert by_tz["UTC"]["offset"] == "UTC+00:00"
    # У всех есть offset в формате UTC±HH:MM
    import re
    rx = re.compile(r"^UTC[+-]\d{2}:\d{2}$")
    for z in zones:
        assert rx.match(z["offset"]), z
        assert isinstance(z["offset_minutes"], int)


def test_list_common_timezones_sorted_west_to_east():
    """Список отсортирован по смещению (запад → восток)."""
    from tzutil import list_common_timezones
    zones = list_common_timezones()
    offsets = [z["offset_minutes"] for z in zones]
    assert offsets == sorted(offsets)


def test_list_common_timezones_all_valid_iana():
    """Каждая `tz` — реально существующая зона (zoneinfo не падает)."""
    from tzutil import list_common_timezones, valid_timezone
    for z in list_common_timezones():
        assert valid_timezone(z["tz"]), z["tz"]


def test_api_timezones_requires_auth_and_returns_list(client):
    # Без авторизации — 401
    assert client.get("/api/timezones").status_code == 401
    body = client.get("/api/timezones", headers=hdr()).json()
    assert isinstance(body, list) and len(body) > 30
    keys = set(body[0].keys())
    assert {"tz", "label", "group", "offset", "offset_minutes"} <= keys


# --- Фаза 10.6: drag-and-drop переупорядочивание ---

def test_db_reorder_task_after_some_neighbor():
    """Двигаем c в позицию сразу после a: было a,b,c → стало a,c,b."""
    from database import add_task, get_tasks, reorder_task
    a = add_task(400, "a")
    b = add_task(400, "b")
    c = add_task(400, "c")
    assert [t["id"] for t in get_tasks(400)] == [a, b, c]
    assert reorder_task(c, after_task_id=a) is True
    assert [t["id"] for t in get_tasks(400)] == [a, c, b]


def test_db_reorder_task_to_beginning_with_none():
    """after=None → задача становится первой."""
    from database import add_task, get_tasks, reorder_task
    a = add_task(401, "a")
    b = add_task(401, "b")
    c = add_task(401, "c")
    assert reorder_task(c, after_task_id=None) is True
    assert [t["id"] for t in get_tasks(401)] == [c, a, b]


def test_db_reorder_task_respects_list_grouping():
    """Сосед `after` обязан быть в той же подгруппе (user+list)."""
    from database import (
        add_task,
        assign_task_to_list,
        create_list,
        get_tasks_by_list,
        reorder_task,
    )
    lid = create_list(402, "L")
    a = add_task(402, "a")                # без списка
    b = add_task(402, "b")                # без списка
    c = add_task(402, "c")
    d = add_task(402, "d")
    assign_task_to_list(c, lid)           # в L
    assign_task_to_list(d, lid)           # тоже в L
    # a в «без списка», c в L — нельзя их связать.
    assert reorder_task(a, after_task_id=c) is False
    # Та же подгруппа — можно.
    assert reorder_task(a, after_task_id=b) is True
    # Реордер внутри именованного списка (покрывает ветку list_id IS NOT NULL).
    assert reorder_task(c, after_task_id=d) is True
    assert [t["id"] for t in get_tasks_by_list(402, lid)] == [d, c]


def test_db_reorder_task_rolls_back_on_db_error(monkeypatch):
    """Сбой в середине UPDATE — целое перенумерование откатывается."""
    import sqlite3

    import database
    from database import add_task, get_tasks, reorder_task
    a = add_task(405, "a")
    add_task(405, "b")
    c = add_task(405, "c")
    before = [t["id"] for t in get_tasks(405)]

    real_conn = database.get_connection

    class CP:
        def __init__(self, c):
            self._c = c
            self._n = 0

        def execute(self, sql, *a, **kw):
            if sql.startswith("UPDATE tasks SET order_index"):
                self._n += 1
                if self._n == 2:
                    raise sqlite3.OperationalError("simulated")
            return self._c.execute(sql, *a, **kw)
        def fetchone(self): return self._c.fetchone()
        def fetchall(self): return self._c.fetchall()

    class CO:
        def __init__(self, c): self._c = c
        @property
        def row_factory(self): return self._c.row_factory
        @row_factory.setter
        def row_factory(self, v): self._c.row_factory = v
        def cursor(self): return CP(self._c.cursor())
        def commit(self): return self._c.commit()
        def rollback(self): return self._c.rollback()
        def close(self): return self._c.close()
        def execute(self, *a, **kw): return self._c.execute(*a, **kw)

    monkeypatch.setattr(database, "get_connection", lambda: CO(real_conn()))
    try:
        reorder_task(c, after_task_id=a)
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("expected OperationalError to propagate")
    monkeypatch.setattr(database, "get_connection", real_conn)
    after = [t["id"] for t in get_tasks(405)]
    assert before == after, "rollback должен оставить порядок прежним"


def test_db_reorder_task_invalid_inputs():
    from database import (
        add_task,
        complete_task,
        get_tasks,
        reorder_task,
    )
    a = add_task(403, "a")
    add_task(403, "b")
    complete_task(a)
    # Выполненная — нельзя
    assert reorder_task(a, after_task_id=None) is False
    # Несуществующая
    assert reorder_task(999999, after_task_id=None) is False
    # Несуществующий after
    z = add_task(404, "z")
    assert reorder_task(z, after_task_id=999999) is False
    # Активные не двинулись.
    assert len(get_tasks(403)) >= 1


def test_api_reorder(client):
    a = client.post("/api/tasks", json={"description": "a"},
                    headers=hdr()).json()["id"]
    b = client.post("/api/tasks", json={"description": "b"},
                    headers=hdr()).json()["id"]
    c = client.post("/api/tasks", json={"description": "c"},
                    headers=hdr()).json()["id"]
    # Двигаем c в начало
    r = client.post(f"/api/tasks/{c}/reorder",
                    json={"after": None}, headers=hdr())
    assert r.status_code == 200 and r.json() == {"moved": True}
    ids = [t["id"] for t in client.get("/api/tasks", headers=hdr()).json()]
    assert ids == [c, a, b]
    # Чужая задача → 404
    assert client.post(f"/api/tasks/{c}/reorder",
                      json={"after": None}, headers=hdr(99)).status_code == 404
    # after — чужая задача → тоже 404 (на _require_own_task)
    assert client.post(f"/api/tasks/{c}/reorder",
                      json={"after": 999999}, headers=hdr()).status_code == 404
    # after — наша задача, но в другом списке → 409 (reorder rejected)
    lid = client.post("/api/lists", json={"name": "L"},
                      headers=hdr()).json()["id"]
    d = client.post("/api/tasks", json={"description": "d"},
                    headers=hdr()).json()["id"]
    client.post(f"/api/tasks/{d}/list",
                json={"list_id": lid}, headers=hdr())
    # c — без списка, d — в L → 409
    assert client.post(f"/api/tasks/{c}/reorder",
                      json={"after": d}, headers=hdr()).status_code == 409


# --- Фаза 10.7: soft-delete + restore + purge для списков ---

def test_db_restore_list_undoes_soft_delete():
    from database import (
        create_list,
        delete_list,
        get_lists,
        restore_list,
    )
    lid = create_list(500, "Work")
    assert delete_list(lid) is True
    assert get_lists(500) == []
    # Восстанавливаем
    assert restore_list(lid) is True
    visible = get_lists(500)
    assert len(visible) == 1 and visible[0]["id"] == lid
    # Уже не deleted → повторный restore False (idempotency)
    assert restore_list(lid) is False
    # Несуществующий
    assert restore_list(999999) is False


def test_db_purge_deleted_lists_after_window():
    """
    purge_deleted_lists удаляет списки, помеченные deleted дольше N
    часов. Тест ставит deleted_at вручную в прошлое.
    """
    from database import (
        add_task,
        assign_task_to_list,
        create_list,
        delete_list,
        get_connection,
        get_lists,
        get_tasks_by_list,
        purge_deleted_lists,
    )
    fresh = create_list(501, "fresh")
    old = create_list(501, "old")
    tid = add_task(501, "t")
    assign_task_to_list(tid, old)
    assert delete_list(fresh) is True
    assert delete_list(old) is True
    # Сдвигаем deleted_at у `old` на 2 дня назад напрямую в БД.
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE lists SET deleted_at = datetime('now', '-2 days') "
        "WHERE id = ?", (old,),
    )
    conn.commit()
    conn.close()
    # Чистим: удалится только `old`, задача отвязалась.
    purged = purge_deleted_lists(older_than_hours=24)
    assert purged == 1
    # Прошёл — fresh ещё здесь (только что удалён)
    all_after = get_lists(501, include_deleted=True)
    assert {x["id"] for x in all_after} == {fresh}
    # Задача из old теперь без списка
    assert [t["id"] for t in get_tasks_by_list(501, None)] == [tid]
    # Повторный purge — 0
    assert purge_deleted_lists(older_than_hours=24) == 0


def test_api_restore_list(client):
    lid = client.post(
        "/api/lists", json={"name": "L"}, headers=hdr()
    ).json()["id"]
    # Активный → restore нельзя
    assert client.post(
        f"/api/lists/{lid}/restore", headers=hdr()
    ).status_code == 404
    # Удаляем (soft)
    assert client.request(
        "DELETE", f"/api/lists/{lid}", headers=hdr()
    ).json() == {"ok": True}
    assert client.get("/api/lists", headers=hdr()).json() == []
    # Чужой → 404
    assert client.post(
        f"/api/lists/{lid}/restore", headers=hdr(99)
    ).status_code == 404
    # Свой → 200, появляется в /api/lists
    r = client.post(f"/api/lists/{lid}/restore", headers=hdr())
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert [x["name"] for x in client.get(
        "/api/lists", headers=hdr()).json()] == ["L"]


def test_db_import_merge_skips_soft_deleted_lists():
    """
    В merge-режиме soft-deleted список НЕ переиспользуется по имени —
    импорт создаёт новый. Иначе восстановление списка было бы скрытым
    побочным эффектом импорта.
    """
    from database import (
        create_list,
        delete_list,
        export_user_data,
        get_lists,
        import_user_data,
    )
    lid = create_list(502, "L")
    payload = export_user_data(502)
    # Удаляем (soft).
    delete_list(lid)
    counts = import_user_data(502, payload, mode="merge")
    assert counts["lists"] == 1   # создан новый, а не «оживлён» старый
    # И deleted'й, и новый присутствуют в полной выборке.
    all_lists = get_lists(502, include_deleted=True)
    assert len([x for x in all_lists if x["name"] == "L"]) == 2


# --- Phase 11.2: Notes ---

def test_db_add_get_update_note():
    from database import (
        add_note,
        get_note,
        get_notes,
        update_note,
    )
    nid = add_note(600, "hello world")
    assert isinstance(nid, int) and nid > 0
    note = get_note(nid)
    assert note["body"] == "hello world"
    assert note["title"] is None
    assert note["pinned"] is False
    assert note["color"] == "#FEF3C7"
    assert note["deleted_at"] is None
    assert update_note(nid, title="Greeting", body="hi", pinned=True,
                       color="#10B981") is True
    note = get_note(nid)
    assert note["title"] == "Greeting"
    assert note["body"] == "hi"
    assert note["pinned"] is True
    assert note["color"] == "#10B981"
    # clear_title
    assert update_note(nid, clear_title=True) is True
    assert get_note(nid)["title"] is None
    # Пустое тело недопустимо
    assert update_note(nid, body="   ") is False
    # Битый цвет
    assert update_note(nid, color="red") is False
    # Ничего не передано — тоже False
    assert update_note(nid) is False
    # Несуществующий
    assert update_note(999999, body="x") is False
    # Отсутствует в get_notes другого пользователя
    assert get_notes(700) == []
    assert any(n["id"] == nid for n in get_notes(600))


def test_db_add_note_validation():
    from database import add_note
    # Пустое тело → None
    assert add_note(601, "   ") is None
    # Битый цвет → None (не сохраняем сломанные данные)
    assert add_note(601, "body", color="not-a-hex") is None


def test_db_get_notes_pinned_first_then_updated_desc():
    """Pinned-first, потом по updated_at DESC (последнее изменение наверху)."""
    import time

    from database import add_note, get_notes, update_note
    a = add_note(602, "first")
    time.sleep(0.05)
    b = add_note(602, "second")
    time.sleep(0.05)
    c = add_note(602, "third")
    # По умолчанию: c, b, a (updated_at desc).
    ids = [n["id"] for n in get_notes(602)]
    assert ids == [c, b, a]
    # Закрепим a → она наверху.
    update_note(a, pinned=True)
    ids = [n["id"] for n in get_notes(602)]
    assert ids[0] == a


def test_db_search_notes():
    from database import add_note, search_notes
    n = add_note(603, "купить хлеб и молоко", title="продукты")
    add_note(603, "позвонить маме")
    # Подстрока в body
    assert [x["id"] for x in search_notes(603, "хлеб")] == [n]
    # Подстрока в title (case-insensitive)
    assert [x["id"] for x in search_notes(603, "ПРОДУКТЫ")] == [n]
    # Не найдено
    assert search_notes(603, "zzz") == []
    # Пустой запрос
    assert search_notes(603, "  ") == []


def test_db_delete_restore_purge_note():
    from database import (
        add_note,
        delete_note,
        get_connection,
        get_note,
        get_notes,
        purge_deleted_notes,
        restore_note,
    )
    nid = add_note(604, "to delete")
    assert delete_note(nid) is True
    assert get_notes(604) == []
    # Видна через get_note (любой статус)
    assert get_note(nid)["deleted_at"] is not None
    # Restore
    assert restore_note(nid) is True
    assert get_notes(604)[0]["id"] == nid
    # Повторный restore — False
    assert restore_note(nid) is False
    # Удаляем снова и сдвигаем deleted_at в прошлое
    delete_note(nid)
    conn = get_connection()
    conn.execute(
        "UPDATE notes SET deleted_at = datetime('now', '-2 days') "
        "WHERE id = ?", (nid,)
    )
    conn.commit()
    conn.close()
    n = purge_deleted_notes(older_than_hours=24)
    assert n == 1
    assert get_note(nid) is None
    # Повторный purge — 0
    assert purge_deleted_notes(older_than_hours=24) == 0


def test_api_notes_crud(client):
    # Создание
    r = client.post(
        "/api/notes",
        json={"body": "первая заметка", "title": "title"},
        headers=hdr(),
    )
    assert r.status_code == 200
    nid = r.json()["id"]
    assert r.json()["title"] == "title" and r.json()["body"] == "первая заметка"
    # Пустое тело → 422
    assert client.post(
        "/api/notes", json={"body": "   "}, headers=hdr()
    ).status_code == 422
    # Список
    lst = client.get("/api/notes", headers=hdr()).json()
    assert isinstance(lst, list) and len(lst) == 1
    # PATCH
    p = client.patch(
        f"/api/notes/{nid}",
        json={"pinned": True, "color": "#10B981"},
        headers=hdr(),
    )
    assert p.status_code == 200 and p.json()["pinned"] is True
    assert p.json()["color"] == "#10B981"
    # Пустой PATCH → 422
    assert client.patch(
        f"/api/notes/{nid}", json={}, headers=hdr()
    ).status_code == 422
    # Чужая → 404
    assert client.patch(
        f"/api/notes/{nid}", json={"body": "x"}, headers=hdr(99)
    ).status_code == 404
    # Поиск
    r2 = client.get(
        "/api/notes?search=первая", headers=hdr()
    ).json()
    assert len(r2) == 1 and r2[0]["id"] == nid


def test_api_note_delete_restore(client):
    nid = client.post(
        "/api/notes", json={"body": "for delete"}, headers=hdr()
    ).json()["id"]
    # Чужой delete → 404
    assert client.request(
        "DELETE", f"/api/notes/{nid}", headers=hdr(99)
    ).status_code == 404
    # Свой delete → 200, исчез из списка
    assert client.request(
        "DELETE", f"/api/notes/{nid}", headers=hdr()
    ).json() == {"ok": True}
    assert client.get("/api/notes", headers=hdr()).json() == []
    # Restore: активный → 404
    nid2 = client.post(
        "/api/notes", json={"body": "active"}, headers=hdr()
    ).json()["id"]
    assert client.post(
        f"/api/notes/{nid2}/restore", headers=hdr()
    ).status_code == 404
    # Чужой → 404
    assert client.post(
        f"/api/notes/{nid}/restore", headers=hdr(99)
    ).status_code == 404
    # Свой deleted → 200, появляется заново
    r = client.post(f"/api/notes/{nid}/restore", headers=hdr())
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert any(n["id"] == nid for n in
               client.get("/api/notes", headers=hdr()).json())


def test_export_import_includes_notes(client):
    nid = client.post(
        "/api/notes",
        json={"body": "carry me", "title": "important"},
        headers=hdr(),
    ).json()["id"]
    client.patch(
        f"/api/notes/{nid}",
        json={"pinned": True, "color": "#FFAA00"},
        headers=hdr(),
    )
    exp = client.get("/api/export", headers=hdr()).json()
    assert isinstance(exp["notes"], list) and len(exp["notes"]) == 1
    src = exp["notes"][0]
    assert src["body"] == "carry me" and src["pinned"] is True
    assert src["color"] == "#FFAA00"
    # Импорт другому пользователю
    r = client.post(
        "/api/import",
        json={"payload": exp, "mode": "merge"},
        headers=hdr(800),
    )
    assert r.status_code == 200 and r.json()["notes"] == 1
    dst = client.get("/api/notes", headers=hdr(800)).json()
    assert len(dst) == 1 and dst[0]["body"] == "carry me"
    assert dst[0]["pinned"] is True
    # Бэкап без notes — не должен ломать импорт
    legacy = {"version": 1, "lists": [], "tasks": []}
    r2 = client.post(
        "/api/import", json={"payload": legacy, "mode": "merge"},
        headers=hdr(800),
    )
    assert r2.status_code == 200 and r2.json()["notes"] == 0


def test_user_stats_includes_notes():
    from database import add_note, get_user_stats
    add_note(900, "a")
    add_note(900, "b")
    s = get_user_stats(900)
    assert s["notes"] == 2


def test_api_create_note_with_pinned_true(client):
    """POST /api/notes принимает pinned и сразу делает PATCH-пин."""
    r = client.post(
        "/api/notes",
        json={"body": "pin me", "pinned": True, "color": "#10B981"},
        headers=hdr(),
    )
    assert r.status_code == 200 and r.json()["pinned"] is True


def test_api_create_note_bad_color_422(client):
    r = client.post(
        "/api/notes", json={"body": "x", "color": "red"}, headers=hdr()
    )
    assert r.status_code == 422


def test_db_import_validates_notes_must_be_list():
    from database import import_user_data
    bad = {"version": 1, "lists": [], "tasks": [], "notes": "no"}
    try:
        import_user_data(901, bad, mode="merge")
    except ValueError as e:
        assert "notes" in str(e).lower()
        return
    raise AssertionError("expected ValueError for bad notes type")


def test_db_import_skips_malformed_notes():
    """Phase 11.2: импорт пропускает кривые элементы в notes."""
    from database import get_notes, import_user_data
    payload = {
        "version": 1, "lists": [], "tasks": [],
        "notes": [
            "not a dict",
            {"body": ""},                   # пустое тело
            {"body": "good", "color": "not-hex"},   # битый цвет → fallback
        ],
    }
    counts = import_user_data(902, payload, mode="merge")
    assert counts["notes"] == 1
    notes = get_notes(902)
    assert len(notes) == 1 and notes[0]["body"] == "good"
    assert notes[0]["color"] == "#FEF3C7"   # fallback дефолт


def test_db_import_replace_wipes_notes():
    from database import (
        add_note,
        export_user_data,
        get_notes,
        import_user_data,
    )
    add_note(903, "to-keep")
    payload = export_user_data(903)
    add_note(903, "garbage")
    # replace: всё стирается, потом импортируется только to-keep.
    counts = import_user_data(903, payload, mode="replace")
    assert counts["notes"] == 1
    bodies = [n["body"] for n in get_notes(903)]
    assert bodies == ["to-keep"]


# --- Phase 11.3: whitelist + whoami ---

def test_is_user_allowed_no_allowlist_means_open():
    """Пустые allowlist'ы → доступ всем (старое поведение)."""
    import config as config_mod
    save_ids = config_mod.ALLOWED_USER_IDS
    save_uns = config_mod.ALLOWED_USERNAMES
    config_mod.ALLOWED_USER_IDS = set()
    config_mod.ALLOWED_USERNAMES = set()
    try:
        assert config_mod.is_user_allowed(42, "anyone") is True
        assert config_mod.is_user_allowed(None, None) is True
    finally:
        config_mod.ALLOWED_USER_IDS = save_ids
        config_mod.ALLOWED_USERNAMES = save_uns


def test_is_user_allowed_by_id_or_username():
    import config as config_mod
    save_ids = config_mod.ALLOWED_USER_IDS
    save_uns = config_mod.ALLOWED_USERNAMES
    config_mod.ALLOWED_USER_IDS = {123}
    config_mod.ALLOWED_USERNAMES = {"e_rnst"}
    try:
        assert config_mod.is_user_allowed(123, None) is True
        assert config_mod.is_user_allowed(999, "e_rnst") is True
        assert config_mod.is_user_allowed(999, "@e_rnst") is True
        assert config_mod.is_user_allowed(999, "someone_else") is False
        assert config_mod.is_user_allowed(None, None) is False
    finally:
        config_mod.ALLOWED_USER_IDS = save_ids
        config_mod.ALLOWED_USERNAMES = save_uns


def test_api_returns_403_when_user_not_in_allowlist(client, monkeypatch):
    """С активным allowlist'ом — любой эндпоинт под current_user_id даёт 403."""
    import config as config_mod
    monkeypatch.setattr(config_mod, "ALLOWED_USER_IDS", {99999})
    monkeypatch.setattr(config_mod, "ALLOWED_USERNAMES", set())
    r = client.get("/api/tasks", headers=hdr(42))   # 42 не в списке
    assert r.status_code == 403


def test_api_allows_user_in_allowlist(client, monkeypatch):
    import config as config_mod
    monkeypatch.setattr(config_mod, "ALLOWED_USER_IDS", {42})
    monkeypatch.setattr(config_mod, "ALLOWED_USERNAMES", set())
    r = client.get("/api/tasks", headers=hdr(42))
    assert r.status_code == 200


def test_api_whoami_no_init_data(client):
    """Без X-Init-Data → ok=False, init_data_present=False."""
    r = client.get("/api/whoami")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["init_data_present"] is False
    assert body["token_set"] is True   # в тестовом окружении токен есть


def test_api_whoami_valid(client):
    r = client.get("/api/whoami", headers=hdr(42))
    body = r.json()
    assert body["ok"] is True
    assert body["allowlist_active"] is False   # дефолт без allowlist


def test_api_whoami_with_allowlist_denied(client, monkeypatch):
    import config as config_mod
    monkeypatch.setattr(config_mod, "ALLOWED_USER_IDS", {99})
    monkeypatch.setattr(config_mod, "ALLOWED_USERNAMES", set())
    body = client.get("/api/whoami", headers=hdr(42)).json()
    assert body["ok"] is True            # подпись валидна
    assert body["allowed"] is False
    assert body["allowlist_active"] is True


def test_scheduler_notify_skips_disallowed_users(monkeypatch):
    """С активным allowlist scheduler не шлёт чужим (но помечает sent)."""
    import asyncio
    from unittest.mock import AsyncMock

    import config as config_mod
    import scheduler
    monkeypatch.setattr(config_mod, "ALLOWED_USER_IDS", {42})

    fake_bot = AsyncMock()
    marked = []
    tasks = [
        {"id": 1, "user_id": 42, "description": "mine"},
        {"id": 2, "user_id": 99, "description": "other"},
    ]
    n = asyncio.run(
        scheduler._notify(fake_bot, tasks, "X", lambda tid: marked.append(tid))
    )
    # Отправили только своему; для чужого вызвали `mark`, чтобы не
    # повторять попытку каждый тик.
    assert n == 1
    fake_bot.send_message.assert_awaited_once()
    assert marked == [1, 2]


# --- Phase 11.4: bulk actions ---

def test_db_bulk_complete():
    from database import (
        add_task,
        bulk_update_tasks,
        get_tasks,
    )
    a = add_task(1000, "a")
    b = add_task(1000, "b")
    c = add_task(1000, "c")
    n = bulk_update_tasks(1000, [a, b], "complete")
    assert n == 2
    # c всё ещё активна
    assert [t["id"] for t in get_tasks(1000)] == [c]
    assert {t["id"] for t in get_tasks(1000, completed=True)} == {a, b}


def test_db_bulk_filters_foreign_ids():
    """Чужие/несуществующие id игнорируются — нельзя через bulk дёрнуть чужое."""
    from database import add_task, bulk_update_tasks, get_tasks
    mine = add_task(1001, "mine")
    other = add_task(1002, "other")
    n = bulk_update_tasks(1001, [mine, other, 999999], "complete")
    assert n == 1     # только своя
    assert get_tasks(1002)[0]["id"] == other  # чужая не тронута


def test_db_bulk_star_unstar_uncomplete():
    from database import (
        add_task,
        bulk_update_tasks,
        complete_task,
        get_tasks,
        set_important,
    )
    a = add_task(1003, "a")
    b = add_task(1003, "b")
    set_important(a, True)
    # unstar
    assert bulk_update_tasks(1003, [a, b], "unstar") == 2
    assert all(t["important"] is False for t in get_tasks(1003))
    # star обратно
    assert bulk_update_tasks(1003, [a, b], "star") == 2
    assert all(t["important"] is True for t in get_tasks(1003))
    # uncomplete после complete
    complete_task(a)
    assert bulk_update_tasks(1003, [a], "uncomplete") == 1
    assert {t["id"] for t in get_tasks(1003)} == {a, b}


def test_db_bulk_move_to_list():
    from database import (
        add_task,
        bulk_update_tasks,
        create_list,
        get_tasks_by_list,
    )
    lid = create_list(1004, "L")
    a = add_task(1004, "a")
    b = add_task(1004, "b")
    add_task(1004, "c")
    assert bulk_update_tasks(1004, [a, b], "move", list_id=lid) == 2
    assert {t["id"] for t in get_tasks_by_list(1004, lid)} == {a, b}
    # move в None = «без списка»
    assert bulk_update_tasks(1004, [a], "move", list_id=None) == 1
    assert {t["id"] for t in get_tasks_by_list(1004, None)} >= {a}


def test_db_bulk_move_rejects_foreign_or_deleted_list():
    import pytest

    from database import (
        add_task,
        bulk_update_tasks,
        create_list,
        delete_list,
    )
    a = add_task(1005, "a")
    foreign = create_list(1006, "L")  # чужой
    with pytest.raises(ValueError):
        bulk_update_tasks(1005, [a], "move", list_id=foreign)
    own = create_list(1005, "Mine")
    delete_list(own)
    with pytest.raises(ValueError):
        bulk_update_tasks(1005, [a], "move", list_id=own)


def test_db_bulk_unknown_action_raises():
    import pytest

    from database import bulk_update_tasks
    with pytest.raises(ValueError):
        bulk_update_tasks(1007, [1], "delete")   # не поддерживаем delete
    with pytest.raises(ValueError):
        bulk_update_tasks(1007, [1], "")


def test_db_bulk_empty_and_garbage_ids():
    from database import bulk_update_tasks
    assert bulk_update_tasks(1008, [], "complete") == 0
    # str, отрицательные, дубликаты — отфильтровываются
    assert bulk_update_tasks(1008, [-1, 0, "abc"], "complete") == 0  # type: ignore


def test_api_bulk_endpoint(client):
    a = client.post("/api/tasks", json={"description": "a"},
                    headers=hdr()).json()["id"]
    b = client.post("/api/tasks", json={"description": "b"},
                    headers=hdr()).json()["id"]
    # Звёздочка двумя задачам пакетом
    r = client.post(
        "/api/tasks/bulk",
        json={"ids": [a, b], "action": "star"}, headers=hdr(),
    )
    assert r.status_code == 200 and r.json()["affected"] == 2
    # Чужие id игнорируются (не 404 — это ожидаемая семантика)
    r2 = client.post(
        "/api/tasks/bulk",
        json={"ids": [a, b], "action": "complete"}, headers=hdr(99),
    )
    assert r2.status_code == 200 and r2.json()["affected"] == 0
    # Битый action → 422
    bad = client.post(
        "/api/tasks/bulk",
        json={"ids": [a], "action": "drop_table"}, headers=hdr(),
    )
    assert bad.status_code == 422


# --- Phase 11.6: task ↔ note linking ---

def test_db_set_task_note_and_query_linked():
    from database import (
        add_note,
        add_task,
        get_task,
        get_tasks_linked_to_note,
        set_task_note,
    )
    nid = add_note(2000, "memo")
    a = add_task(2000, "ref this")
    b = add_task(2000, "ref this too")
    add_task(2000, "unrelated")
    assert set_task_note(a, nid) is True
    assert set_task_note(b, nid) is True
    assert get_task(a)["note_id"] == nid
    assert {t["id"] for t in get_tasks_linked_to_note(2000, nid)} == {a, b}
    assert set_task_note(a, None) is True
    assert get_task(a)["note_id"] is None
    assert [t["id"] for t in get_tasks_linked_to_note(2000, nid)] == [b]
    assert set_task_note(999999, nid) is False
    assert get_tasks_linked_to_note(2001, nid) == []


def test_db_get_tasks_linked_excludes_completed():
    from database import (
        add_note,
        add_task,
        complete_task,
        get_tasks_linked_to_note,
        set_task_note,
    )
    nid = add_note(2002, "memo")
    a = add_task(2002, "todo")
    b = add_task(2002, "done")
    set_task_note(a, nid)
    set_task_note(b, nid)
    complete_task(b)
    assert [t["id"] for t in get_tasks_linked_to_note(2002, nid)] == [a]


def test_api_patch_task_with_note_id(client):
    nid = client.post(
        "/api/notes", json={"body": "memo"}, headers=hdr()
    ).json()["id"]
    tid = client.post(
        "/api/tasks", json={"description": "x"}, headers=hdr()
    ).json()["id"]
    r = client.patch(
        f"/api/tasks/{tid}", json={"note_id": nid}, headers=hdr()
    )
    assert r.status_code == 200 and r.json()["note_id"] == nid
    foreign = client.post(
        "/api/notes", json={"body": "their"}, headers=hdr(99)
    ).json()["id"]
    assert client.patch(
        f"/api/tasks/{tid}", json={"note_id": foreign}, headers=hdr()
    ).status_code == 404
    r3 = client.patch(
        f"/api/tasks/{tid}", json={"clear_note": True}, headers=hdr()
    )
    assert r3.status_code == 200 and r3.json()["note_id"] is None


def test_api_note_tasks_endpoint(client):
    nid = client.post(
        "/api/notes", json={"body": "memo"}, headers=hdr()
    ).json()["id"]
    a = client.post(
        "/api/tasks", json={"description": "linked"}, headers=hdr()
    ).json()["id"]
    client.patch(
        f"/api/tasks/{a}", json={"note_id": nid}, headers=hdr()
    )
    body = client.get(f"/api/notes/{nid}/tasks", headers=hdr()).json()
    assert len(body) == 1 and body[0]["id"] == a
    assert client.get(
        f"/api/notes/{nid}/tasks", headers=hdr(99)
    ).status_code == 404


# --- Phase 11.10: soft-delete + restore + purge tasks ---

def test_db_delete_task_hides_from_lists():
    from database import (
        add_task,
        delete_task,
        get_tasks,
    )
    a = add_task(3000, "keep")
    b = add_task(3000, "drop")
    assert delete_task(b) is True
    # «drop» исчезла из активных
    assert [t["id"] for t in get_tasks(3000)] == [a]
    # Повторный delete → False
    assert delete_task(b) is False
    # Несуществующая → False
    assert delete_task(999999) is False


def test_db_deleted_task_excluded_from_all_views():
    """Удалённая задача не должна вылезать ни в одном эндпоинте."""
    from database import (
        add_task,
        add_to_myday,
        bulk_update_tasks,
        delete_task,
        get_important_tasks,
        get_myday,
        get_planned,
        get_tasks,
        get_tasks_by_list,
        search_tasks,
        set_deadline,
        set_important,
        set_reminder_at,
    )
    tid = add_task(3001, "ghost")
    set_important(tid, True)
    set_deadline(tid, "2026-12-31 23:00:00")
    set_reminder_at(tid, "2026-12-31 22:00:00")
    add_to_myday(tid, "2026-05-21")
    delete_task(tid)
    assert get_tasks(3001) == []
    assert get_tasks_by_list(3001, None) == []
    assert get_myday(3001, "2026-05-21") == []
    assert get_planned(3001) == []
    assert get_important_tasks(3001) == []
    assert search_tasks(3001, "ghost") == []
    # bulk тоже не трогает (фильтр deleted_at IS NULL)
    assert bulk_update_tasks(3001, [tid], "star") == 0


def test_db_restore_task_brings_it_back():
    from database import (
        add_task,
        delete_task,
        get_tasks,
        restore_task,
    )
    tid = add_task(3002, "phoenix")
    delete_task(tid)
    assert get_tasks(3002) == []
    assert restore_task(tid) is True
    assert [t["id"] for t in get_tasks(3002)] == [tid]
    # Повторный restore — False
    assert restore_task(tid) is False
    # Несуществующая
    assert restore_task(999999) is False


def test_db_purge_deleted_tasks_after_window():
    from database import (
        add_task,
        delete_task,
        get_connection,
        get_task,
        purge_deleted_tasks,
    )
    fresh = add_task(3003, "fresh")
    old = add_task(3003, "old")
    delete_task(fresh)
    delete_task(old)
    # Сдвигаем deleted_at у `old` в прошлое.
    conn = get_connection()
    conn.execute(
        "UPDATE tasks SET deleted_at = datetime('now', '-2 days') "
        "WHERE id = ?", (old,)
    )
    conn.commit()
    conn.close()
    n = purge_deleted_tasks(older_than_hours=24)
    assert n == 1
    assert get_task(old) is None         # реально удалена
    assert get_task(fresh) is not None   # ещё в окне отмены
    # Повторный purge — 0
    assert purge_deleted_tasks(older_than_hours=24) == 0


def test_api_delete_restore_task(client):
    tid = client.post(
        "/api/tasks", json={"description": "doomed"}, headers=hdr()
    ).json()["id"]
    # Чужой DELETE → 404
    assert client.request(
        "DELETE", f"/api/tasks/{tid}", headers=hdr(99)
    ).status_code == 404
    # Свой DELETE → 200, исчезла из /api/tasks
    assert client.request(
        "DELETE", f"/api/tasks/{tid}", headers=hdr()
    ).json() == {"ok": True}
    assert client.get("/api/tasks", headers=hdr()).json() == []
    # Restore: чужой → 404, свой → 200, появилась
    assert client.post(
        f"/api/tasks/{tid}/restore", headers=hdr(99)
    ).status_code == 404
    r = client.post(f"/api/tasks/{tid}/restore", headers=hdr())
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert [t["id"] for t in client.get(
        "/api/tasks", headers=hdr()).json()] == [tid]
    # Restore активной (уже не удалённой) → 404
    assert client.post(
        f"/api/tasks/{tid}/restore", headers=hdr()
    ).status_code == 404


def test_api_patch_blocked_on_deleted_task(client):
    """После DELETE задача недоступна для PATCH/complete — 404."""
    tid = client.post(
        "/api/tasks", json={"description": "x"}, headers=hdr()
    ).json()["id"]
    client.request("DELETE", f"/api/tasks/{tid}", headers=hdr())
    assert client.patch(
        f"/api/tasks/{tid}", json={"important": True}, headers=hdr()
    ).status_code == 404
    assert client.post(
        f"/api/tasks/{tid}/complete", headers=hdr()
    ).status_code == 404


# --- Phase 11.11: архив выполненных + меню команд бота ---

def test_db_get_archived_tasks_newest_first():
    from database import (
        add_task,
        complete_task,
        delete_task,
        get_archived_tasks,
    )
    a = add_task(4000, "first done")
    b = add_task(4000, "later done")
    c = add_task(4000, "active")
    deleted = add_task(4000, "deleted done")
    complete_task(a)
    complete_task(b)
    complete_task(deleted)
    delete_task(deleted)            # выполнено + удалено → не в архиве
    archive = get_archived_tasks(4000)
    # `c` активная → не в архиве; `deleted` удалена → не в архиве.
    # `b` завершилась позже → её id больше → выше.
    assert [t["id"] for t in archive] == [b, a]
    assert c not in [t["id"] for t in archive]


def test_db_get_archived_tasks_user_isolated():
    from database import add_task, complete_task, get_archived_tasks
    a = add_task(4001, "x")
    complete_task(a)
    # Другой пользователь — ничего не видит.
    assert get_archived_tasks(4002) == []


def test_api_archive_endpoint(client):
    a = client.post("/api/tasks", json={"description": "todo"},
                    headers=hdr()).json()["id"]
    b = client.post("/api/tasks", json={"description": "done"},
                    headers=hdr()).json()["id"]
    client.post(f"/api/tasks/{b}/complete", headers=hdr())
    # Архив содержит только выполненную, новейшую сверху.
    archive = client.get("/api/archive", headers=hdr()).json()
    assert [t["id"] for t in archive] == [b]
    assert a not in [t["id"] for t in archive]
    # 401 без авторизации
    assert client.get("/api/archive").status_code == 401


# --- Phase 11.19: напоминания для заметок ---

def test_db_set_note_reminder_and_query_due():
    from database import (
        add_note,
        get_due_note_reminders,
        get_note,
        mark_note_reminder_sent,
        set_note_reminder,
    )
    nid = add_note(5000, "ping me")
    # Прошлое время → due сразу
    assert set_note_reminder(nid, "2020-01-01 00:00:00") is True
    assert get_note(nid)["reminder_at"] == "2020-01-01 00:00:00"
    due = get_due_note_reminders("2026-12-31 00:00:00")
    assert [n["id"] for n in due] == [nid]
    # Mark sent
    assert mark_note_reminder_sent(nid) is True
    assert get_due_note_reminders("2026-12-31 00:00:00") == []
    # Снять напоминание
    assert set_note_reminder(nid, None) is True
    assert get_note(nid)["reminder_at"] is None
    # Несуществующая заметка
    assert set_note_reminder(999999, "2026-01-01 00:00:00") is False
    assert mark_note_reminder_sent(999999) is False


def test_db_due_note_reminders_excludes_deleted_and_future():
    from database import (
        add_note,
        delete_note,
        get_due_note_reminders,
        set_note_reminder,
    )
    a = add_note(5001, "delete me later")
    b = add_note(5001, "future")
    set_note_reminder(a, "2020-01-01 00:00:00")
    set_note_reminder(b, "2099-01-01 00:00:00")
    delete_note(a)
    due = get_due_note_reminders("2026-01-01 00:00:00")
    # `a` удалена → исключена; `b` в будущем → не due.
    assert due == []


def test_api_patch_note_with_reminder(client):
    """PATCH /api/notes/{id} устанавливает и снимает reminder_at."""
    nid = client.post(
        "/api/notes", json={"body": "ping"}, headers=hdr()
    ).json()["id"]
    # Поставить напоминание
    r = client.patch(
        f"/api/notes/{nid}",
        json={"reminder_at": "2030-01-01 09:00"}, headers=hdr(),
    )
    assert r.status_code == 200 and r.json()["reminder_at"]
    # Очистить
    r2 = client.patch(
        f"/api/notes/{nid}", json={"clear_reminder": True}, headers=hdr()
    )
    assert r2.status_code == 200 and r2.json()["reminder_at"] is None
    # Чужая → 404
    assert client.patch(
        f"/api/notes/{nid}",
        json={"reminder_at": "2030-01-01 09:00"}, headers=hdr(99),
    ).status_code == 404


def test_api_patch_note_only_reminder_no_other_changes(client):
    """Если в PATCH только reminder/clear_reminder — это валидно (не 422)."""
    nid = client.post(
        "/api/notes", json={"body": "x"}, headers=hdr()
    ).json()["id"]
    r = client.patch(
        f"/api/notes/{nid}",
        json={"reminder_at": "2030-05-05 12:00"}, headers=hdr(),
    )
    assert r.status_code == 200


def test_scheduler_sends_note_reminder(monkeypatch):
    """Phase 11.19: check_and_send_reminders теперь поднимает заметки."""
    import asyncio
    from unittest.mock import AsyncMock

    import config as config_mod
    save_ids = config_mod.ALLOWED_USER_IDS
    config_mod.ALLOWED_USER_IDS = set()
    try:
        from database import (
            add_note,
            get_note,
            set_note_reminder,
        )
        from scheduler import check_and_send_reminders
        nid = add_note(5002, "drink water")
        set_note_reminder(nid, "2020-01-01 00:00:00")
        fake_bot = AsyncMock()
        n = asyncio.run(check_and_send_reminders(fake_bot))
        assert n >= 1
        # Отправили текст с префиксом «📓 Заметка».
        sent_args = [c for c in fake_bot.send_message.await_args_list
                     if c.kwargs.get("chat_id") == 5002]
        assert sent_args
        text = sent_args[0].kwargs["text"]
        assert "📓 Заметка" in text
        # reminder_sent помечен — повторный вызов ничего не шлёт.
        assert get_note(nid)["reminder_sent"] == 1
        fake_bot.reset_mock()
        m = asyncio.run(check_and_send_reminders(fake_bot))
        # Может быть >0 для других тестов, но для нашей заметки — нет.
        sent2 = [c for c in fake_bot.send_message.await_args_list
                 if c.kwargs.get("chat_id") == 5002]
        assert not sent2
        del m
    finally:
        config_mod.ALLOWED_USER_IDS = save_ids

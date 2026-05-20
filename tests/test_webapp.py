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


def test_healthz(client):
    assert client.get("/healthz").json() == {"ok": True}


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

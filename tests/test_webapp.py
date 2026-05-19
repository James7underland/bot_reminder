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

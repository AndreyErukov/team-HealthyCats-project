"""Интеграционные тесты настоящего SQLite-бэкенда."""
from datetime import date

import pytest

import database
from app import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "USE_DEMO": False,
        "SECRET_KEY": "backend-tests-only",
        "DATABASE_PATH": str(tmp_path / "test.db"),
        "TIMEZONE": "UTC",
    })


def csrf_token(client):
    client.get("/auth")
    with client.session_transaction() as state:
        return state["csrf_token"]


def post(client, path, values=None):
    return client.post(path, data={"csrf_token": csrf_token(client), **(values or {})},
                       follow_redirects=False)


def register(client, login="alice", name="Алиса", password="safe-password-123"):
    return post(client, "/register", {
        "name": name, "login": login, "password": password,
    })


def enable_all_days(client):
    with client.session_transaction() as state:
        user_id = state["user_id"]
    database.save_user_schedule(user_id, list(range(7)), True)


def create_habit(client, **updates):
    values = {
        "name": "Читать каждый день",
        "type": "useful",
        "trigger": "вечернего чая",
        "action": "прочитаю 10 страниц",
        "period": "evening",
        "goal": "10 страниц",
        "minimum": "1 страница",
        "days": [str(i) for i in range(7)],
    }
    values.update(updates)
    response = post(client, "/habits/save", values)
    assert response.status_code == 303
    with client.session_transaction() as state:
        user_id = state["user_id"]
    return database.get_user_habits(user_id)[-1]


def test_register_and_password_is_hashed(app):
    client = app.test_client()
    response = register(client)
    assert response.status_code == 303
    with client.session_transaction() as state:
        user_id = state["user_id"]
    saved = database.get_user_by_id(user_id)
    assert saved["login"] == "alice"
    assert saved["password_hash"] != "safe-password-123"
    assert client.get("/today").status_code == 200


def test_registration_rejects_weak_password_and_duplicate_login(app):
    client = app.test_client()
    assert register(client, password="123").status_code == 400
    client2 = app.test_client()
    assert register(client2).status_code == 303
    client3 = app.test_client()
    duplicate = register(client3)
    assert duplicate.status_code == 400
    assert "логин" in duplicate.get_data(as_text=True).lower()


def test_login_logout_and_private_routes(app):
    client = app.test_client()
    register(client)
    client.get("/logout")
    assert client.get("/today").status_code == 302
    logged = post(client, "/login", {"login": "alice", "password": "safe-password-123"})
    assert logged.status_code == 303
    assert client.get("/settings").status_code == 200
    assert client.get("/logout").status_code == 302
    assert client.get("/habits").status_code == 302


def test_invalid_login_does_not_create_session(app):
    client = app.test_client()
    response = post(client, "/login", {"login": "missing", "password": "no-password"})
    assert response.status_code == 401
    assert client.get("/today").status_code == 302


def test_csrf_required_for_mutations(app):
    client = app.test_client()
    register(client)
    response = client.post("/habits/save", data={"name": "Неверный запрос"})
    assert response.status_code == 400


def test_habit_crud_logging_and_idempotency(app):
    client = app.test_client()
    register(client)
    enable_all_days(client)
    habit = create_habit(client)

    assert client.get("/habits").status_code == 200
    assert post(client, f"/habits/{habit['id']}/log", {"status": "done"}).status_code == 303
    assert post(client, f"/habits/{habit['id']}/log", {"status": "done"}).status_code == 303

    with client.session_transaction() as state:
        rows = database.get_user_logs(state["user_id"], date.today().isoformat(), date.today().isoformat())
        user_id = state["user_id"]
    assert len(rows) == 1
    assert rows[0]["status"] == "done"

    assert post(client, f"/habits/{habit['id']}/log", {"status": "reset"}).status_code == 303
    assert database.get_user_logs(user_id, date.today().isoformat(), date.today().isoformat()) == []


def test_minimum_counts_as_progress(app):
    client = app.test_client()
    register(client)
    enable_all_days(client)
    habit = create_habit(client)
    assert post(client, f"/habits/{habit['id']}/log", {"status": "minimum"}).status_code == 303
    page = client.get("/statistics")
    assert page.status_code == 200
    assert "Минимумы — тоже прогресс" in page.get_data(as_text=True)


def test_user_cannot_access_another_users_habit(app):
    owner = app.test_client()
    register(owner)
    enable_all_days(owner)
    habit = create_habit(owner)

    other = app.test_client()
    register(other, login="bob", name="Боб", password="another-password-1")
    assert other.get(f"/habits/{habit['id']}/edit").status_code == 404
    assert post(other, f"/habits/{habit['id']}/log", {"status": "done"}).status_code == 404


def test_pause_blocks_logging_and_resume_reenables_it(app):
    client = app.test_client()
    register(client)
    enable_all_days(client)
    habit = create_habit(client)
    paused = post(client, "/schedule/save", {
        "intent": "pause", "duration": "today",
        "days": [str(i) for i in range(7)], "reminders": "on",
    })
    assert paused.status_code == 303
    assert post(client, f"/habits/{habit['id']}/log", {"status": "done"}).status_code == 303
    with client.session_transaction() as state:
        user_id = state["user_id"]
    assert database.get_user_logs(user_id) == []

    assert post(client, "/schedule/save", {"intent": "resume"}).status_code == 303
    assert post(client, f"/habits/{habit['id']}/log", {"status": "done"}).status_code == 303
    assert len(database.get_user_logs(user_id)) == 1


def test_support_skip_persists_reason_without_progress(app):
    client = app.test_client()
    register(client)
    enable_all_days(client)
    habit = create_habit(client)
    assert post(client, "/support/skip", {"reason": "energy"}).status_code == 303
    with client.session_transaction() as state:
        rows = database.get_user_logs(state["user_id"])
    row = next(item for item in rows if item["habit_id"] == habit["id"])
    assert row["status"] == "skipped"
    assert row["reason"] == "energy"


def test_invalid_support_reason_is_rejected(app):
    client = app.test_client()
    register(client)
    enable_all_days(client)
    create_habit(client)
    assert post(client, "/support/skip", {"reason": "not-a-reason"}).status_code == 400


def test_templates_statistics_and_schedule_render(app):
    client = app.test_client()
    register(client)
    for path in ("/today", "/habits", "/habits/new", "/support", "/statistics", "/schedule", "/settings"):
        response = client.get(path)
        assert response.status_code == 200, path
    assert client.get("/statistics?month=13").status_code == 400


def test_sqlite_survives_new_app_instance(app):
    client = app.test_client()
    register(client)
    enable_all_days(client)
    habit = create_habit(client)
    post(client, f"/habits/{habit['id']}/log", {"status": "done"})
    db_path = app.config["DATABASE_PATH"]

    restarted = create_app({
        "TESTING": True, "USE_DEMO": False, "SECRET_KEY": "restart-test-key",
        "DATABASE_PATH": db_path, "TIMEZONE": "UTC",
    })
    second = restarted.test_client()
    assert second.get("/today").status_code == 302
    assert post(second, "/login", {"login": "alice", "password": "safe-password-123"}).status_code == 303
    with second.session_transaction() as state:
        user_id = state["user_id"]
    assert len(database.get_user_habits(user_id)) == 1
    rows = database.get_user_logs(user_id, date.today().isoformat(), date.today().isoformat())
    assert len(rows) == 1
    assert rows[0]["status"] == "done"


def test_health_endpoint_is_public(app):
    assert app.test_client().get("/health").json == {"status": "ok"}

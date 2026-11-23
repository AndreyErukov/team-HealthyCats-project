"""Проверки контрактов демо-стенда. Запуск: python -m pytest -q."""
import re
import pytest
from app import create_app


@pytest.fixture()
def client():
    app = create_app({"TESTING": True, "SECRET_KEY": "only-for-tests"})
    with app.test_client() as client:
        client.get("/today")
        yield client


def post(client, path, data=None, follow_redirects=True):
    with client.session_transaction() as session:
        token = session["csrf_token"]
    return client.post(path, data={"csrf_token": token, **(data or {})}, follow_redirects=follow_redirects)


def habit_data(**updates):
    return {"name": "Зарядка утром", "type": "useful", "trigger": "умывания",
            "action": "сделаю зарядку", "period": "morning", "goal": "5 минут",
            "minimum": "1 минута", "days": ["0", "2", "4"], **updates}


def counter(response):
    html = response.get_data(as_text=True)
    match = re.search(r'class="plan-counter"[^>]*><strong>(\d+)</strong> из (\d+) выполнено', html)
    assert match, "Счётчик отсутствует"
    return tuple(map(int, match.groups()))


@pytest.mark.parametrize("path", ["/today", "/habits", "/habits?type=replacement", "/habits/new",
                                    "/habits/new?limit=1", "/habits/1/edit", "/support", "/statistics",
                                    "/schedule", "/settings", "/auth", "/auth?tab=register"])
def test_pages_render(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert '<html lang="ru"' in response.get_data(as_text=True)
    assert "бережно" in response.get_data(as_text=True)
    html = response.get_data(as_text=True)
    assert html.index('css/style.css') < html.index('css/motion.css')
    assert html.index('js/motion.js') < html.index('js/main.js') < html.index('js/today.js')


@pytest.mark.parametrize("path", ["/static/css/style.css", "/static/css/motion.css", "/static/js/main.js", "/static/js/motion.js", "/static/js/today.js", "/static/fonts/Manrope-variable.woff2", "/static/favicon.svg"])
def test_assets_are_local(client, path):
    assert client.get(path).status_code == 200


def test_initial_unique_tasks(client):
    assert counter(client.get("/today")) == (2, 4)


@pytest.mark.parametrize("status", ["done", "minimum"])
def test_log_updates_demo_counter(client, status):
    response = post(client, "/habits/3/log", {"status": status})
    assert counter(response) == (3, 4)
    # Повторная отправка не дублирует выполнение.
    assert counter(post(client, "/habits/3/log", {"status": status})) == (3, 4)
    assert counter(post(client, "/habits/3/log", {"status": "reset"})) == (2, 4)


@pytest.mark.parametrize("token", [None, "wrong-token", "неверный-токен"])
def test_csrf_rejects_invalid_token(client, token):
    data = {"status": "done"}
    if token is not None:
        data["csrf_token"] = token
    response = client.post("/habits/3/log", data=data)
    assert response.status_code == 400
    assert counter(client.get("/today")) == (2, 4)


def test_invalid_log_status(client):
    assert post(client, "/habits/3/log", {"status": "unknown"}).status_code == 400


def test_unknown_habit(client):
    assert client.get("/habits/999/edit").status_code == 404
    assert post(client, "/habits/999/log", {"status": "done"}).status_code == 404


def test_get_cannot_mark_habit(client):
    assert client.get("/habits/1/log").status_code == 405


def test_create_then_edit(client):
    response = post(client, "/habits/save", habit_data())
    assert response.status_code == 200
    assert "Зарядка утром" in response.get_data(as_text=True)
    assert counter(client.get("/today")) == (2, 5)
    edited = post(client, "/habits/save", habit_data(id="5", name="Зарядка без спешки"))
    assert "Зарядка без спешки" in edited.get_data(as_text=True)
    assert counter(client.get("/today")) == (2, 5)


@pytest.mark.parametrize("updates", [{"days": []}, {"name": ""}, {"type": "replacement", "replacement_plan": ""},
                                    {"name": "я" * 101}, {"type": "unknown"}, {"period": "night"}])
def test_habit_validation_preserves_form(client, updates):
    response = post(client, "/habits/save", habit_data(**updates))
    assert response.status_code == 400
    assert "Давай кое-что уточним" in response.get_data(as_text=True)
    assert counter(client.get("/today")) == (2, 4)


def test_user_text_is_escaped(client):
    payload = '<script>alert("x")</script>'
    response = post(client, "/habits/save", habit_data(name=payload))
    html = response.get_data(as_text=True)
    assert payload not in html
    assert "&lt;script&gt;" in html


def test_soft_step_is_not_completion(client):
    response = post(client, "/support/step", {"reason": "energy"})
    assert "Прочитать 1 страницу" in response.get_data(as_text=True)
    assert counter(response) == (2, 4)
    assert counter(post(client, "/habits/1/log", {"status": "minimum"})) == (3, 4)


def test_skip_is_not_completion(client):
    response = post(client, "/support/skip", {"reason": "time"})
    assert "На сегодня пропущено" in response.get_data(as_text=True)
    assert counter(response) == (2, 4)


def test_invalid_reason(client):
    assert post(client, "/support/step", {"reason": "unknown"}).status_code == 400


def test_pause_prevents_demo_logging(client):
    response = post(client, "/schedule/save", {"intent": "pause", "duration": "today", "days": ["0", "1"]})
    assert "Пауза включена" in response.get_data(as_text=True)
    assert counter(post(client, "/habits/3/log", {"status": "done"})) == (2, 4)
    post(client, "/schedule/save", {"intent": "resume"})
    assert counter(post(client, "/habits/3/log", {"status": "done"})) == (3, 4)


@pytest.mark.parametrize("data", [
    {"duration": "dates", "start": "2026-11-10", "end": "2026-11-09", "days": ["0"]},
    {"duration": "dates", "start": "", "end": "bad-date", "days": ["0"]},
    {"duration": "today", "days": []},
])
def test_schedule_validation(client, data):
    assert post(client, "/schedule/save", data).status_code == 400


def test_reminders_can_be_disabled(client):
    response = post(client, "/schedule/save", {"intent": "save", "duration": "today", "days": ["0"]})
    checkbox = re.search(r'<input[^>]+name="reminders"[^>]+>', response.get_data(as_text=True)).group()
    assert "checked" not in checkbox


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_demo_auth_redirects_without_storing_password(client, path):
    password = "NEVER-STORE-THIS-DEMO-STRING"
    response = post(client, path, {"login": "demo", "name": "Демо", "password": password}, follow_redirects=False)
    assert response.status_code == 303
    assert response.location.endswith("/today")
    assert password not in str(response.headers)
    with client.session_transaction() as session:
        assert password not in str(dict(session))


def test_reset_demo(client):
    post(client, "/habits/3/log", {"status": "done"})
    post(client, "/demo/reset")
    assert counter(client.get("/today")) == (2, 4)


def test_logout_is_only_demo_session_reset(client):
    post(client, "/habits/3/log", {"status": "done"})
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    assert "Не вводи настоящий пароль" in response.get_data(as_text=True)
    assert counter(client.get("/today")) == (2, 4)


def test_heatmap_has_real_november_dates(client):
    html = client.get("/statistics").get_data(as_text=True)
    dates = re.findall(r'data-heat-day="(\d+)"', html)
    assert list(map(int, dates)) == list(range(1, 31))
    for level in range(5):
        assert f"heat-level-{level}" in html


def test_unknown_page_has_friendly_404(client):
    response = client.get("/unknown-page")
    assert response.status_code == 404
    assert "К сегодняшнему плану" in response.get_data(as_text=True)



def test_today_progressive_enhancement_contract(client):
    html = client.get("/today").get_data(as_text=True)
    states = dict(re.findall(r'data-task-id="(\d+)"\s+data-task-status="([^\"]+)"', html))
    assert states == {"1": "pending", "2": "done", "3": "pending", "4": "minimum"}
    forms = re.findall(r'<form\b[^>]*data-habit-log[^>]*>.*?</form>', html, re.S)
    assert len(forms) == 4
    assert all('method="post"' in form and 'name="csrf_token"' in form for form in forms)
    assert 'data-plan-paused="false"' in html
    assert 'class="plan-counter" aria-live="polite" aria-atomic="true"' in html


def test_xhr_uses_same_post_redirect_html_contract(client):
    with client.session_transaction() as session:
        token = session["csrf_token"]
    response = client.post("/habits/3/log", data={"csrf_token": token, "status": "minimum"},
                           headers={"X-Requested-With": "XMLHttpRequest", "Accept": "text/html"})
    assert response.status_code == 303
    html_response = client.get(response.location)
    assert counter(html_response) == (3, 4)
    assert re.search(r'data-task-id="3"\s+data-task-status="minimum"', html_response.get_data(as_text=True))
    assert html_response.headers["Cache-Control"] == "no-store"
    bad = client.post("/habits/3/log", data={"status": "reset"},
                      headers={"X-Requested-With": "XMLHttpRequest"})
    assert bad.status_code == 400
    assert counter(client.get("/today")) == (3, 4)

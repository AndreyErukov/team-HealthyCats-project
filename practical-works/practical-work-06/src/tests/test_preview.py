"""Регрессия для встроенного превью: формы должны работать без cookies."""
import re
from urllib.parse import urlencode
import pytest
from app import create_app


@pytest.fixture()
def preview(monkeypatch):
    monkeypatch.setenv("PREVIEW_MODE", "1")
    app = create_app({"TESTING": True, "SECRET_KEY": "preview-only-test-key"})
    return app.test_client(use_cookies=False)


def fields(response):
    html = response.get_data(as_text=True)
    return {
        name: re.search(r'name="' + name + r'"\s+value="([^"]+)"', html).group(1)
        for name in ("csrf_token", "demo_token")
    }


def test_demo_logs_and_messages_work_without_cookies(preview):
    first = preview.get("/", follow_redirects=True)
    data = fields(first)
    response = preview.post("/habits/1/log", data={**data, "status": "done"}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '<strong>3</strong> из 4 выполнено' in html
    assert "Выполнение отмечено в демо" in html
    assert response.headers["Cache-Control"] == "no-store"
    # Обычный переход переносит тот же подписанный идентификатор в URL.
    url = "/today?" + urlencode({"_demo": data["demo_token"]})
    again = preview.get(url).get_data(as_text=True)
    assert '<strong>3</strong> из 4 выполнено' in again


def test_cookie_free_preview_still_requires_csrf_and_valid_signature(preview):
    data = fields(preview.get("/today"))
    bad_csrf = preview.post("/habits/1/log", data={**data, "status": "done", "csrf_token": "wrong"})
    bad_signature = preview.post("/habits/1/log", data={**data, "status": "done", "demo_token": "wrong"})
    missing = preview.post("/habits/1/log", data={"status": "done"})
    assert bad_csrf.status_code == bad_signature.status_code == missing.status_code == 400
    unchanged = preview.get("/today?" + urlencode({"_demo": data["demo_token"]})).get_data(as_text=True)
    assert '<strong>2</strong> из 4 выполнено' in unchanged


def test_cookie_free_auth_form_and_logout(preview):
    data = fields(preview.get("/auth"))
    logged_in = preview.post("/login", data={**data, "login": "demo", "password": "demo-only"}, follow_redirects=True)
    assert logged_in.status_code == 200
    assert 'Демо-вход выполнен' in logged_in.get_data(as_text=True)
    token = fields(logged_in)["demo_token"]
    logged_out = preview.get("/logout?" + urlencode({"_demo": token}), follow_redirects=True)
    assert logged_out.status_code == 200
    assert fields(logged_out)["demo_token"] != token

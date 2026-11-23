"""Flask-стенд для HTML/Jinja-фронтенда HealthyCats.

Это НЕ production-бэкенд. Нет БД, авторизации, LLM и расчёта серий.
POST-маршруты нужны для проверки форм; изменения живут в памяти процесса.
Точки будущей интеграции отмечены TODO(INTEGRATION).
"""
from copy import deepcopy
from datetime import date
import hmac
import os
import secrets
from threading import RLock
from collections import OrderedDict

from flask import (Flask, abort, g, redirect, render_template, request, session, url_for,
                   flash as flask_flash, get_flashed_messages as flask_messages)
from itsdangerous import URLSafeSerializer, BadSignature
from demo_data import (DATE_LABEL, DEMO_DATE, USER, DAYS, PERIODS, REASONS, TEMPLATES,
                       STATS, HEATMAP, fresh_state, empty_habit)


def create_app(test_config=None):
    app = Flask(__name__)
    # HTTPS-превью внутри iframe: отдельная partitioned-cookie (Flask 3.1+).
    # При обычном локальном запуске остаётся SameSite=Lax, без Secure.
    preview_mode = os.environ.get("PREVIEW_MODE") == "1"
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=64 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="None" if preview_mode else "Lax",
        SESSION_COOKIE_SECURE=preview_mode,
        SESSION_COOKIE_PARTITIONED=preview_mode,
    )
    if test_config:
        app.config.update(test_config)

    # Демонстрационный store. В cookie — только случайный идентификатор и CSRF.
    # Не использовать вместо репозитория БД в рабочем приложении.
    states = OrderedDict()
    lock = RLock()

    def get_state():
        if "demo_id" not in session:
            session["demo_id"] = secrets.token_urlsafe(24)
        sid = session["demo_id"]
        with lock:
            if sid not in states:
                states[sid] = fresh_state()
            states.move_to_end(sid)
            # Защита демонстрационного процесса от бесконечного роста памяти.
            while len(states) > 250:
                states.popitem(last=False)
            return states[sid]

    # Некоторые встроенные превью не передают cookies. Только для демо
    # переносим случайный ID сессии в подписанном токене; CSRF остаётся включён.
    # Это не механизм авторизации: в такой ссылке нет данных пользователя.
    preview_signer = URLSafeSerializer(app.config["SECRET_KEY"], salt="berezhno-preview")

    @app.before_request
    def protect_forms():
        if request.endpoint == "static":
            return
        if preview_mode:
            token = request.args.get("_demo") or request.form.get("demo_token", "")
            sid = session.get("demo_id")
            if token:
                try:
                    sid = preview_signer.loads(token)
                    if not isinstance(sid, str) or not 16 <= len(sid) <= 100:
                        raise BadSignature("Invalid demo session id")
                except BadSignature:
                    if request.method == "POST":
                        abort(400, description="Демо-сессия устарела. Обнови страницу и повтори действие.")
                    sid = None
            session["demo_id"] = sid or secrets.token_urlsafe(24)
            g.demo_token = preview_signer.dumps(session["demo_id"])
            session["csrf_token"] = get_state().setdefault("_csrf_token", secrets.token_urlsafe(24))
        if request.method == "POST":
            expected = session.get("csrf_token", "")
            supplied = request.form.get("csrf_token", "")
            if not expected or not hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8")):
                abort(400, description="Форма устарела. Обнови страницу и попробуй ещё раз.")
        session.setdefault("csrf_token", secrets.token_urlsafe(24))

    @app.url_defaults
    def keep_preview_session(endpoint, values):
        token = getattr(g, "demo_token", None) if preview_mode else None
        if token and endpoint != "static":
            values.setdefault("_demo", token)

    @app.after_request
    def avoid_stale_forms(response):
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "same-origin"
        return response

    def flash(message, category="message"):
        if preview_mode:
            get_state().setdefault("_messages", []).append((category, message))
        else:
            flask_flash(message, category)

    def messages(with_categories=False):
        if not preview_mode:
            return flask_messages(with_categories=with_categories)
        pending = get_state().pop("_messages", [])
        return pending if with_categories else [message for _, message in pending]

    @app.context_processor
    def common_context():
        return {"user": USER, "days": DAYS, "periods": PERIODS,
                "csrf_token": session.get("csrf_token", ""),
                "demo_token": getattr(g, "demo_token", ""),
                "get_flashed_messages": messages,
                "habit_count": len(get_state()["habits"]), "demo_date": DEMO_DATE}

    @app.template_filter("day_word")
    def day_word(value):
        n = abs(int(value))
        return "дней" if 11 <= n % 100 <= 14 else ("день" if n % 10 == 1 else "дня" if n % 10 in (2, 3, 4) else "дней")

    @app.template_filter("schedule_label")
    def schedule_label(values):
        if len(values) == 7:
            return "Каждый день"
        if values == [0, 1, 2, 3, 4]:
            return "5 дней в неделю"
        return ", ".join(DAYS[int(d)]["short"] for d in values)

    def find_habit(habit_id):
        habit = next((h for h in get_state()["habits"] if h["id"] == habit_id), None)
        if habit is None:
            abort(404)
        return habit

    def focus_habit():
        habits = get_state()["habits"]
        return next((h for h in habits if h["is_focus"]), habits[0] if habits else None)

    @app.get("/")
    def index():
        return redirect(url_for("today"))

    @app.get("/today")
    def today():
        state = get_state()
        # TODO(INTEGRATION): daily_planner.py. Сейчас все тестовые привычки
        # входят в фиксированный дневной сценарий, независимо от расписания.
        tasks = state["habits"]
        focus = focus_habit()
        groups = [{**period, "tasks": [h for h in tasks if h["period"] == period["id"] and h != focus]}
                  for period in PERIODS]
        completed = sum(state["logs"].get(h["id"]) in ("done", "minimum") for h in tasks)
        return render_template("today.html", active="today", date_label=DATE_LABEL,
                               focus=focus, groups=groups, logs=state["logs"],
                               completed=completed, total=len(tasks), stats=STATS,
                               soft_habit_id=state["soft_habit_id"], paused=state["schedule"]["pause_active"])

    @app.post("/habits/<int:habit_id>/log")
    def log_habit(habit_id):
        state = get_state()
        find_habit(habit_id)
        status = request.form.get("status")
        if status not in ("done", "minimum", "reset"):
            abort(400, description="Неизвестная отметка выполнения.")
        if state["schedule"]["pause_active"]:
            flash("Сейчас включена демо-пауза. Сначала возобнови привычки в расписании.", "info")
        elif status == "reset":
            state["logs"].pop(habit_id, None)
            flash("Отметка отменена. Можно выбрать другой шаг.", "info")
        else:
            # TODO(INTEGRATION): запись в БД и пересчёт через streak_calculator.py.
            state["logs"][habit_id] = status
            flash("Минимум — тоже прогресс. Шаг отмечен в демо." if status == "minimum"
                  else "Ещё один маленький шаг. Выполнение отмечено в демо.", "success")
        return redirect(url_for("today"), code=303)

    @app.get("/habits")
    def habits():
        selected = request.args.get("type", "all")
        if selected not in ("all", "useful", "replacement"):
            selected = "all"
        # TODO(INTEGRATION): habits_manager.filter_and_sort_habits.
        items = sorted(get_state()["habits"], key=lambda h: not h["is_focus"])
        counts = {"all": len(items), "useful": sum(h["type"] == "useful" for h in items),
                  "replacement": sum(h["type"] == "replacement" for h in items)}
        return render_template("habits.html", active="habits", habits=items, selected=selected, counts=counts)

    def render_habit_form(form, errors=None, status=200):
        # TODO(INTEGRATION): check_habit_limit. ?limit=1 демонстрирует баннер.
        return render_template("habit_form.html", active="habits", form=form,
                               errors=errors or [], templates=TEMPLATES,
                               limit_warning=request.args.get("limit") == "1"), status

    @app.get("/habits/new")
    def new_habit():
        return render_habit_form(empty_habit())

    @app.get("/habits/<int:habit_id>/edit")
    def edit_habit(habit_id):
        return render_habit_form(deepcopy(find_habit(habit_id)))

    @app.post("/habits/save")
    def save_habit():
        state = get_state()
        form = empty_habit()
        errors = []
        limits = {"name": 100, "trigger": 160, "action": 160, "goal": 120,
                  "minimum": 120, "replacement_plan": 400}
        for key, limit in limits.items():
            form[key] = request.form.get(key, "").strip()
            if len(form[key]) > limit:
                errors.append(f"Поле «{key}» не должно превышать {limit} символов.")
        if any(not form[k] for k in ("name", "trigger", "action", "goal", "minimum")):
            errors.append("Заполни название, формулу действия, обычный шаг и минимум.")
        form["type"] = request.form.get("type", "useful")
        form["period"] = request.form.get("period", "day")
        if form["type"] not in ("useful", "replacement") or form["period"] not in ("morning", "day", "evening"):
            errors.append("Выбери тип привычки и время суток из предложенных вариантов.")
        if form["type"] == "replacement" and not form["replacement_plan"]:
            errors.append("Добавь мягкое действие для плана замены.")
        form["days"] = sorted({int(d) for d in request.form.getlist("days") if d in {str(i) for i in range(7)}})
        if not form["days"]:
            errors.append("Выбери хотя бы один день недели.")
        form["is_focus"] = request.form.get("is_focus") == "on"
        existing = None
        if request.form.get("id"):
            try:
                existing = find_habit(int(request.form["id"]))
                form["id"] = existing["id"]
            except ValueError:
                abort(400, description="Некорректный идентификатор привычки.")
        if errors:
            return render_habit_form(form, errors, 400)
        if len(state["habits"]) >= 30 and existing is None:
            return render_habit_form(form, ["Демонстрационное хранилище заполнено. Сбрось демо-данные в настройках."], 400)
        # TODO(INTEGRATION): habits_manager + БД. Это лишь echo-store формы.
        habit = {**form, "id": existing["id"] if existing else max((h["id"] for h in state["habits"]), default=0) + 1,
                 "task": form["name"], "minimum_task": "Минимум: " + form["minimum"],
                 "duration": "В своём темпе", "icon": "sprout" if form["type"] == "replacement" else "leaf",
                 "color": "rose" if form["type"] == "replacement" else "sage",
                 "streak": existing["streak"] if existing else 0,
                 "clean_days": existing["clean_days"] if existing else 0}
        if existing:
            habit["icon"], habit["color"] = existing["icon"], existing["color"]
            if all(form[k] == existing[k] for k in ("name", "action", "goal")):
                habit["task"], habit["duration"] = existing["task"], existing["duration"]
        if habit["is_focus"]:
            for other in state["habits"]:
                other["is_focus"] = False
        if existing:
            state["habits"] = [habit if h["id"] == existing["id"] else h for h in state["habits"]]
        else:
            state["habits"].append(habit)
        flash("Привычка обновлена в демо." if existing else "Новая привычка добавлена в демо. Начни с малого!", "success")
        return redirect(url_for("habits"), code=303)

    @app.get("/support")
    def support():
        return render_template("support.html", active="support", reasons=REASONS,
                               selected_reason=get_state()["reason"], focus=focus_habit())

    @app.post("/support/<action>")
    def support_action(action):
        if action not in ("step", "skip"):
            abort(404)
        state = get_state()
        reason = request.form.get("reason")
        if reason not in {r["id"] for r in REASONS}:
            abort(400, description="Выбери причину из списка.")
        # TODO(INTEGRATION): miss_support.record_miss_reason / get_soft_next_step.
        state["reason"] = reason
        focus = focus_habit()
        if focus and state["logs"].get(focus["id"]) not in ("done", "minimum"):
            if action == "step":
                state["soft_habit_id"] = focus["id"]
                state["logs"].pop(focus["id"], None)
                flash("На сегодня выбран мягкий шаг. Отметь его, когда выполнишь — сейчас выполнение не засчитано.", "success")
            else:
                state["logs"][focus["id"]] = "skipped"
                flash("Сегодня можно выдохнуть. В демо отмечен пропуск без штрафов.", "info")
        else:
            flash("Фокус дня уже выполнен. Причина сохранена только в демо.", "info")
        return redirect(url_for("today"), code=303)

    @app.get("/statistics")
    def statistics():
        return render_template("statistics.html", active="statistics", stats=STATS, heatmap=HEATMAP)

    @app.get("/schedule")
    def schedule():
        return render_template("schedule.html", active="habits", schedule=get_state()["schedule"], errors=[])

    @app.post("/schedule/save")
    def save_schedule():
        state = get_state()
        intent = request.form.get("intent", "save")
        if intent not in ("save", "pause", "resume"):
            abort(400, description="Неизвестное действие с расписанием.")
        if intent == "resume":
            state["schedule"]["pause_active"] = False
            flash("Демо-пауза выключена. Возвращайся в комфортном темпе.", "success")
            return redirect(url_for("schedule"), code=303)
        values = deepcopy(state["schedule"])
        values.update(duration=request.form.get("duration", "today"),
                      days=sorted({int(d) for d in request.form.getlist("days") if d in {str(i) for i in range(7)}}),
                      reminders=request.form.get("reminders") == "on")
        errors = []
        if not values["days"]:
            errors.append("Оставь хотя бы один рабочий день. Для полного отдыха включи паузу.")
        if values["duration"] == "dates":
            values["start"] = request.form.get("start", "")
            values["end"] = request.form.get("end", "")
            try:
                if date.fromisoformat(values["end"]) <= date.fromisoformat(values["start"]):
                    errors.append("Дата возобновления должна быть позже даты начала.")
            except ValueError:
                errors.append("Укажи корректные даты начала и возобновления.")
        elif values["duration"] != "today":
            errors.append("Выбери срок паузы из предложенных вариантов.")
        if errors:
            return render_template("schedule.html", active="habits", schedule=values, errors=errors), 400
        # TODO(INTEGRATION): pause_manager.py. Автопродление/напоминания НЕ реализованы.
        if intent == "pause":
            values["pause_active"] = True
        state["schedule"] = values
        flash("Пауза включена в демо. История отметок не изменена." if intent == "pause"
              else "Расписание сохранено в демо. Уведомления пока не отправляются.", "success")
        return redirect(url_for("schedule"), code=303)

    @app.get("/settings")
    def settings():
        return render_template("settings.html", active="settings")

    @app.post("/demo/reset")
    def reset_demo():
        with lock:
            states[session["demo_id"]] = fresh_state()
        flash("Демо-данные сброшены. Тема и размер шрифта сохранены.", "success")
        return redirect(url_for("settings"), code=303)

    @app.get("/auth")
    def auth():
        return render_template("auth.html", tab="register" if request.args.get("tab") == "register" else "login", error="")

    @app.route("/login", methods=["GET", "POST"])
    @app.route("/register", methods=["GET", "POST"])
    def demo_auth():
        if request.method == "GET":
            return redirect(url_for("auth", tab="register" if request.path == "/register" else "login"))
        # TODO(INTEGRATION): auth.py. Любые данные принимаются; пароль НЕ читаем,
        # НЕ сохраняем и НЕ пишем в логи. Пользователь всегда тестовый Евгений.
        flash("Демо-вход выполнен. Настоящая авторизация пока не подключена.", "info")
        return redirect(url_for("today"), code=303)

    @app.get("/logout")
    def logout():
        # TODO(INTEGRATION): auth.py. Пока только завершение демо-сессии.
        with lock:
            states.pop(session.get("demo_id"), None)
        session.clear()
        g.demo_token = None
        return redirect(url_for("auth"))

    @app.errorhandler(404)
    @app.errorhandler(400)
    @app.errorhandler(413)
    def error_page(error):
        message = "Похоже, такой страницы нет. Давай вернёмся к твоему плану." if error.code == 404 else error.description
        return render_template("error.html", active="", code=error.code, message=message), error.code

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)

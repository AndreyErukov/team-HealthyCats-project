"""Рабочая Flask-сборка HealthyCats: SQLite, авторизация и реальные данные."""
import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

import database
import auth
import habits_manager
import daily_planner
import streak_calculator
import statistics_heatmap
import miss_support
import ai_client
import schedule_adapter
from algorithms.pause_manager import build_pause_range, is_date_paused
from demo_data import DAYS, PERIODS


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE_PATH=os.environ.get("HEALTHYCATS_DATABASE", str(Path(__file__).with_name("berezhno.db"))),
        TIMEZONE=os.environ.get("HEALTHYCATS_TIMEZONE", "Europe/Moscow"),
        MAX_CONTENT_LENGTH=64 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,
    )
    if test_config:
        app.config.update(test_config)

    database.DB_PATH = Path(app.config["DATABASE_PATH"])
    database.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    database.init_db()

    public_endpoints = {"static", "auth_page", "login", "register", "health"}
    valid_reasons = {item["id"] for item in miss_support.get_reasons()}

    def current_date():
        try:
            return datetime.now(ZoneInfo(app.config["TIMEZONE"])).date()
        except (ZoneInfoNotFoundError, ValueError):
            return date.today()

    def current_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        user = database.get_user_by_id(user_id)
        if user is None:
            session.clear()
            return None
        return user

    @app.before_request
    def protect_forms_and_private_pages():
        if request.endpoint == "static":
            return None
        session.setdefault("csrf_token", secrets.token_urlsafe(32))
        if request.method == "POST":
            expected = session.get("csrf_token", "")
            supplied = request.form.get("csrf_token", "")
            if not expected or not secrets.compare_digest(expected, supplied):
                abort(400, description="Форма устарела. Обнови страницу и попробуй ещё раз.")
        if request.endpoint not in public_endpoints:
            user = current_user()
            if user is None:
                return redirect(url_for("auth_page", tab="login"))
            g.user = user
        else:
            g.user = current_user()
        return None

    @app.after_request
    def secure_html_responses(response):
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "same-origin"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.context_processor
    def common_context():
        user = getattr(g, "user", None) or {"id": None, "name": "Гость", "login": ""}
        return {
            "user": user, "days": DAYS, "periods": PERIODS,
            "csrf_token": session.get("csrf_token", ""), "demo_token": "",
            "demo_mode": False,
            "habit_count": len(database.get_user_habits(user["id"])) if user.get("id") else 0,
        }

    @app.template_filter("day_word")
    def day_word(value):
        n = abs(int(value))
        if 11 <= n % 100 <= 14:
            return "дней"
        return "день" if n % 10 == 1 else "дня" if n % 10 in (2, 3, 4) else "дней"

    @app.template_filter("schedule_label")
    def schedule_label(values):
        values = sorted(int(value) for value in values)
        if len(values) == 7:
            return "Каждый день"
        if values == [0, 1, 2, 3, 4]:
            return "5 дней в неделю"
        return ", ".join(DAYS[value]["short"] for value in values)

    def form_context(form, errors=None, status=200):
        habits = database.get_user_habits(g.user["id"])
        return render_template(
            "habit_form.html", active="habits", form=form,
            errors=errors or [], templates=habits_manager.get_templates(),
            limit_warning=habits_manager.check_habit_limit(habits),
        ), status

    def get_owned_habit(habit_id):
        habit = database.get_habit_by_id(habit_id, g.user["id"])
        if habit is None:
            abort(404, description="Привычка не найдена.")
        return habit

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def index():
        return redirect(url_for("today"))

    @app.get("/today")
    def today():
        target = current_date()
        plan = daily_planner.build_daily_plan(g.user["id"], target)
        plan["stats"] = streak_calculator.build_user_stats(g.user["id"], target)
        plan["tip"] = miss_support.get_daily_tip(target)
        soft_habit_id = session.get("soft_habit_id")
        if session.get("soft_habit_date") != target.isoformat():
            soft_habit_id = None
        plan["soft_habit_id"] = soft_habit_id
        return render_template("today.html", active="today", **plan)

    @app.get("/habits")
    def habits():
        selected = request.args.get("type", "all")
        items, counts = habits_manager.filter_and_sort_habits(
            database.get_user_habits(g.user["id"]), selected
        )
        items = streak_calculator.enrich_habit_metrics(g.user["id"], items, current_date())
        if selected not in ("all", "useful", "replacement"):
            selected = "all"
        return render_template("habits.html", active="habits", habits=items,
                               selected=selected, counts=counts)

    @app.get("/habits/new")
    def new_habit():
        form = {
            "id": None, "name": "", "type": "useful", "trigger": "", "action": "",
            "period": "day", "goal": "", "minimum": "", "days": [0, 1, 2, 3, 4],
            "is_focus": False, "replacement_plan": "", "icon": "leaf", "color": "sage",
        }
        template_id = request.args.get("template")
        if template_id:
            values = habits_manager.create_from_template(template_id)
            if values is None:
                abort(404, description="Шаблон не найден.")
            form.update(values)
        return form_context(form)

    @app.get("/habits/<int:habit_id>/edit")
    def edit_habit(habit_id):
        return form_context(get_owned_habit(habit_id))

    @app.post("/habits/save")
    def save_habit():
        data, errors = habits_manager.validate_habit_form(request.form)
        habit_id = request.form.get("id", "").strip()
        if habit_id:
            try:
                data["id"] = int(habit_id)
                get_owned_habit(data["id"])
            except (TypeError, ValueError):
                abort(400, description="Некорректный идентификатор привычки.")
        else:
            data["id"] = None
        if errors:
            return form_context(data, errors, 400)
        saved_id = database.save_habit(g.user["id"], data)
        session.pop("soft_habit_id", None)
        session.pop("soft_habit_date", None)
        flash("Привычка сохранена.", "success")
        return redirect(url_for("edit_habit", habit_id=saved_id), code=303)

    @app.post("/habits/<int:habit_id>/log")
    def log_habit(habit_id):
        habit = get_owned_habit(habit_id)
        status = request.form.get("status", "")
        if status not in {"done", "minimum", "reset"}:
            abort(400, description="Неизвестная отметка выполнения.")
        target = current_date()
        settings = database.get_user_schedule(g.user["id"])
        pauses = database.get_user_pauses(g.user["id"])
        if is_date_paused(target.isoformat(), pauses):
            flash("Сейчас действует пауза. Можно вернуться к привычкам позже.", "info")
            return redirect(url_for("today"), code=303)
        effective = set(habit["days"]) & set(settings["work_days"])
        if status != "reset" and target.weekday() not in effective:
            flash("Сегодня эта привычка не входит в расписание.", "info")
            return redirect(url_for("today"), code=303)
        if status == "reset":
            database.delete_habit_log(g.user["id"], habit_id, target.isoformat())
            flash("Отметка отменена.", "info")
        else:
            database.upsert_habit_log(g.user["id"], habit_id, target.isoformat(), status)
            flash("Минимум — тоже прогресс. Отметка сохранена." if status == "minimum"
                  else "Выполнение сохранено. Хороший шаг!", "success")
        if session.get("soft_habit_id") == habit_id:
            session.pop("soft_habit_id", None)
            session.pop("soft_habit_date", None)
        return redirect(url_for("today"), code=303)

    @app.get("/support")
    def support():
        plan = daily_planner.build_daily_plan(g.user["id"], current_date())
        focus = plan["focus"]
        selected = session.get("selected_reason", "time")
        suggestion = ai_client.analyze_miss(selected, focus)
        return render_template("support.html", active="support",
                               reasons=miss_support.get_reasons(),
                               selected_reason=selected, focus=focus,
                               suggestion=suggestion)

    @app.post("/support/<action>")
    def support_action(action):
        if action not in {"step", "skip"}:
            abort(404)
        reason = request.form.get("reason", "")
        if reason not in valid_reasons:
            abort(400, description="Выбери причину из списка.")
        plan = daily_planner.build_daily_plan(g.user["id"], current_date())
        focus = plan["focus"]
        session["selected_reason"] = reason
        if focus is None:
            flash("Сначала добавь привычку в свой план.", "info")
        elif plan["paused"]:
            flash("Сейчас действует пауза. Отдых тоже часть плана.", "info")
        elif plan["logs"].get(focus["id"]) in {"done", "minimum"}:
            flash("Фокус уже отмечен. Можно спокойно оставить день как есть.", "info")
        elif action == "step":
            session["soft_habit_id"] = focus["id"]
            session["soft_habit_date"] = current_date().isoformat()
            flash("Мягкий шаг выбран. Выполнение будет засчитано только после отдельной отметки.", "success")
        else:
            miss_support.record_miss_reason(g.user["id"], focus["id"],
                                            current_date().isoformat(), reason)
            session.pop("soft_habit_id", None)
            session.pop("soft_habit_date", None)
            flash("Пропуск сохранён без штрафов. Можно вернуться в следующий подходящий день.", "info")
        return redirect(url_for("today"), code=303)

    @app.get("/statistics")
    def statistics():
        target = current_date()
        try:
            year = int(request.args.get("year", target.year))
            month = int(request.args.get("month", target.month))
            if not 2000 <= year <= 2100 or not 1 <= month <= 12:
                raise ValueError
        except ValueError:
            abort(400, description="Некорректный месяц статистики.")
        label, label_year = statistics_heatmap.month_label(year, month)
        return render_template(
            "statistics.html", active="statistics",
            stats=streak_calculator.build_user_stats(g.user["id"], target),
            heatmap=statistics_heatmap.build_heatmap_matrix(g.user["id"], year, month),
            month_name=label, month_year=label_year,
        )

    @app.get("/schedule")
    def schedule():
        target = current_date()
        schedule_data = database.get_user_schedule(g.user["id"])
        pauses = database.get_user_pauses(g.user["id"])
        active = next((p for p in pauses if p["start_date"] <= target.isoformat() < p["end_date"] and p["is_active"]), None)
        schedule_data.update(
            pause_active=active is not None,
            duration="dates" if active and active["start_date"] != target.isoformat() else "today",
            start=active["start_date"] if active else target.isoformat(),
            end=active["end_date"] if active else (target + timedelta(days=1)).isoformat(),
            days=schedule_data["work_days"],
        )
        return render_template(
            "schedule.html", active="habits", schedule=schedule_data, errors=[],
            recommendation=schedule_adapter.analyze_habit_load(g.user["id"], target),
        )

    @app.post("/schedule/save")
    def save_schedule():
        intent = request.form.get("intent", "save")
        if intent not in {"save", "pause", "resume"}:
            abort(400, description="Неизвестное действие с расписанием.")
        if intent == "resume":
            database.deactivate_pauses(g.user["id"])
            flash("Пауза завершена. Отметки и история сохранены.", "success")
            return redirect(url_for("schedule"), code=303)
        raw_days = request.form.getlist("days")
        work_days = sorted({int(item) for item in raw_days if item in {str(n) for n in range(7)}})
        values = database.get_user_schedule(g.user["id"])
        values.update(work_days=work_days, days=work_days,
                      reminders=request.form.get("reminders") == "on",
                      duration=request.form.get("duration", "today"),
                      start=request.form.get("start", ""), end=request.form.get("end", ""),
                      pause_active=False)
        errors = []
        if not work_days:
            errors.append("Оставь хотя бы один рабочий день.")
        pause_range = None
        if intent == "pause":
            pause_range = build_pause_range(values["duration"], current_date().isoformat(),
                                            values["start"], values["end"])
            if not pause_range["is_valid"]:
                errors.append(pause_range["error"])
        if errors:
            return render_template("schedule.html", active="habits", schedule=values,
                                   errors=errors,
                                   recommendation=schedule_adapter.analyze_habit_load(g.user["id"], current_date())), 400
        database.save_user_schedule(g.user["id"], work_days, values["reminders"])
        if intent == "pause":
            database.create_pause(g.user["id"], pause_range["start_date"], pause_range["end_date"])
            flash("Пауза сохранена. История выполнения осталась на месте.", "success")
        else:
            flash("Расписание сохранено.", "success")
        return redirect(url_for("schedule"), code=303)

    @app.get("/settings")
    def settings():
        return render_template("settings.html", active="settings")

    @app.get("/auth")
    def auth_page():
        return render_template("auth.html",
                               tab="register" if request.args.get("tab") == "register" else "login",
                               error="")

    @app.post("/register")
    def register():
        try:
            user_id = auth.register_user(request.form.get("name"),
                                         request.form.get("login"),
                                         request.form.get("password"))
        except auth.AuthError as exc:
            return render_template("auth.html", tab="register", error=str(exc)), 400
        session.clear()
        session["user_id"] = user_id
        session["csrf_token"] = secrets.token_urlsafe(32)
        session.permanent = True
        flash("Аккаунт создан. Добро пожаловать!", "success")
        return redirect(url_for("today"), code=303)

    @app.post("/login")
    def login():
        user = auth.authenticate_user(request.form.get("login"), request.form.get("password"))
        if user is None:
            return render_template("auth.html", tab="login",
                                   error="Не удалось войти. Проверь логин и пароль."), 401
        session.clear()
        session["user_id"] = user["id"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        session.permanent = True
        flash("С возвращением!", "success")
        return redirect(url_for("today"), code=303)

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("auth_page", tab="login"))

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        if error.code in {400, 404, 413}:
            message = error.description
            if error.code == 404:
                message = "Похоже, такой страницы нет. Давай вернёмся к своему плану."
            return render_template("error.html", active="", code=error.code, message=message), error.code
        return error

    return app

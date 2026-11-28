"""Подготовка дневного плана из SQLite, индивидуального и общего расписания."""
from datetime import date

import database
from demo_data import DAYS, PERIODS
from algorithms.pause_manager import get_effective_days, is_date_paused


_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
_WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")


def is_habit_scheduled(habit, target_date, global_work_days):
    effective = get_effective_days(habit.get("days", []), global_work_days)
    return target_date.weekday() in effective


def build_daily_plan(user_id, target_date=None):
    target_date = target_date or date.today()
    date_key = target_date.isoformat()
    habits = database.get_user_habits(user_id)
    settings = database.get_user_schedule(user_id)
    pauses = database.get_user_pauses(user_id)
    paused = is_date_paused(date_key, pauses)

    tasks = [
        habit for habit in habits
        if is_habit_scheduled(habit, target_date, settings["work_days"])
    ]
    logs = {
        int(item["habit_id"]): item["status"]
        for item in database.get_user_logs(user_id, date_key, date_key)
    }
    focus = next((habit for habit in tasks if habit.get("is_focus")), None)
    if focus is None and tasks:
        focus = tasks[0]

    groups = []
    for period in PERIODS:
        groups.append({
            **period,
            "tasks": [
                habit for habit in tasks
                if habit.get("period") == period["id"] and (focus is None or habit["id"] != focus["id"])
            ],
        })

    completed = sum(logs.get(habit["id"]) in {"done", "minimum"} for habit in tasks)
    return {
        "date_label": f"{_WEEKDAYS[target_date.weekday()].capitalize()}, {target_date.day} {_MONTHS[target_date.month - 1]}",
        "focus": focus,
        "groups": groups,
        "logs": logs,
        "completed": completed,
        "total": len(tasks),
        "paused": paused,
        "habits": tasks,
        "soft_habit_id": None,
        "target_date": date_key,
    }

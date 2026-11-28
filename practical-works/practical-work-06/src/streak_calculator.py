"""Расчёт серий и сводных показателей из фактической истории отметок.

На этапе интеграции серия означает календарные дни, в которые отмечен хотя бы
один done/minimum. День без запланированных привычек и активная пауза серию
не прерывают. Пропуск и отсутствие выполнения в запланированный день — прерывают.
Это простое и проверяемое правило; оно требует согласования с командой.
"""
from collections import defaultdict
from datetime import date, timedelta

import database
from algorithms.pause_manager import is_date_paused


SUCCESS = {"done", "minimum"}


def _scheduled_habits(habits, work_days, target_date):
    weekdays = set(work_days)
    return [
        habit for habit in habits
        if target_date.weekday() in (set(habit.get("days", [])) & weekdays)
    ]


def build_user_stats(user_id, target_date=None):
    target_date = target_date or date.today()
    all_logs = database.get_user_logs(user_id)
    logs_by_day = defaultdict(list)
    by_habit_day = {}
    for row in all_logs:
        logs_by_day[row["log_date"]].append(row)
        by_habit_day[(int(row["habit_id"]), row["log_date"])] = row["status"]

    habits = database.get_user_habits(user_id)
    settings = database.get_user_schedule(user_id)
    pauses = database.get_user_pauses(user_id)

    first_date = min(
        (date.fromisoformat(row["log_date"]) for row in all_logs),
        default=target_date,
    )
    streak = 0
    longest = 0
    run = 0
    cursor = first_date
    while cursor <= target_date:
        key = cursor.isoformat()
        if is_date_paused(key, pauses):
            cursor += timedelta(days=1)
            continue
        scheduled = _scheduled_habits(habits, settings["work_days"], cursor)
        if not scheduled:
            cursor += timedelta(days=1)
            continue
        progress = any(row["status"] in SUCCESS for row in logs_by_day.get(key, []))
        if progress:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
        cursor += timedelta(days=1)

    cursor = target_date
    while cursor >= first_date:
        key = cursor.isoformat()
        if is_date_paused(key, pauses):
            cursor -= timedelta(days=1)
            continue
        scheduled = _scheduled_habits(habits, settings["work_days"], cursor)
        if not scheduled:
            cursor -= timedelta(days=1)
            continue
        if any(row["status"] in SUCCESS for row in logs_by_day.get(key, [])):
            streak += 1
            cursor -= timedelta(days=1)
            continue
        # Сегодняшний незавершённый план ещё не обрывает серию.
        if cursor == target_date:
            cursor -= timedelta(days=1)
            continue
        break

    week_start = target_date - timedelta(days=6)
    planned = completed = minimums = 0
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        key = day.isoformat()
        if is_date_paused(key, pauses):
            continue
        for habit in _scheduled_habits(habits, settings["work_days"], day):
            planned += 1
            status = by_habit_day.get((habit["id"], key))
            if status in SUCCESS:
                completed += 1
            if status == "minimum":
                minimums += 1

    return {
        "streak": streak,
        "longest": longest,
        "completed": completed,
        "planned": planned,
        "minimums": minimums,
    }



def enrich_habit_metrics(user_id, habits, target_date=None):
    """Добавляет в карточки привычек текущую серию и дни без срыва."""
    target_date = target_date or date.today()
    settings = database.get_user_schedule(user_id)
    pauses = database.get_user_pauses(user_id)
    logs = database.get_user_logs(user_id)
    by_habit = defaultdict(dict)
    for row in logs:
        by_habit[int(row["habit_id"])][row["log_date"]] = row["status"]

    for habit in habits:
        history = by_habit.get(habit["id"], {})
        try:
            created = date.fromisoformat(str(habit.get("created_at", ""))[:10])
        except ValueError:
            created = target_date

        scheduled_days = set(habit.get("days", [])) & set(settings["work_days"])
        streak = 0
        cursor = target_date
        while cursor >= created:
            key = cursor.isoformat()
            if is_date_paused(key, pauses) or cursor.weekday() not in scheduled_days:
                cursor -= timedelta(days=1)
                continue
            status = history.get(key)
            if status in SUCCESS:
                streak += 1
                cursor -= timedelta(days=1)
                continue
            if cursor == target_date and status is None:
                cursor -= timedelta(days=1)
                continue
            break

        habit["streak"] = streak
        if habit.get("type") == "replacement":
            relapse_dates = [
                date.fromisoformat(day)
                for day, status in history.items()
                if status == "relapse"
            ]
            clean_since = max(relapse_dates) if relapse_dates else created
            habit["clean_days"] = max(0, (target_date - clean_since).days)
        else:
            habit["clean_days"] = 0

    return habits

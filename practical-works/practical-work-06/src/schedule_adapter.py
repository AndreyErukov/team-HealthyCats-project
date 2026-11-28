"""Ненавязчивая рекомендация по нагрузке на основе реальных пропусков."""
from collections import Counter
from datetime import date, timedelta

import database


_DAY_FORMS = ("понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье")


def analyze_habit_load(user_id, target_date=None):
    target_date = target_date or date.today()
    start = (target_date - timedelta(days=29)).isoformat()
    logs = database.get_user_logs(user_id, start, target_date.isoformat())
    skipped = Counter()
    for row in logs:
        if row["status"] == "skipped":
            skipped[date.fromisoformat(row["log_date"]).weekday()] += 1
    settings = database.get_user_schedule(user_id)
    candidates = [(count, day) for day, count in skipped.items() if day in settings["work_days"]]
    if not candidates:
        return None
    count, day = max(candidates)
    if count < 2:
        return None
    return {
        "day": day,
        "day_label": _DAY_FORMS[day],
        "count": count,
        "title": f"Облегчить план в { _DAY_FORMS[day] }?",
        "description": f"За последние 30 дней в этот день отмечено {count} пропуска. Можно убрать его из рабочих дней или оставить только одну привычку.",
    }

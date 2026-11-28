from datetime import datetime, timedelta


def is_date_paused(target_date, pauses):
    for pause in pauses:
        if pause.get("is_active") != 1:
            continue

        if pause["start_date"] <= target_date < pause["end_date"]:
            return True

    return False


def build_pause_range(duration, today_date, start="", end=""):
    if duration == "today":
        try:
            today = datetime.strptime(today_date, "%Y-%m-%d").date()
        except ValueError:
            return {
                "is_valid": False,
                "start_date": "",
                "end_date": "",
                "error": "Неверный формат сегодняшней даты."
            }

        return {
            "is_valid": True,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=1)).isoformat(),
            "error": None
        }

    if duration == "dates":
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            return {
                "is_valid": False,
                "start_date": start,
                "end_date": end,
                "error": "Даты должны быть в формате YYYY-MM-DD."
            }

        if end_date <= start_date:
            return {
                "is_valid": False,
                "start_date": start,
                "end_date": end,
                "error": "Дата возобновления должна быть позже даты начала."
            }

        return {
            "is_valid": True,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "error": None
        }

    return {
        "is_valid": False,
        "start_date": "",
        "end_date": "",
        "error": "Неизвестный тип паузы."
    }


def get_effective_days(habit_days, global_work_days):
    if global_work_days is None:
        return sorted(habit_days)

    return sorted(set(habit_days) & set(global_work_days))


if __name__ == "__main__":
    pauses = [
        {
            "start_date": "2026-11-09",
            "end_date": "2026-11-11",
            "is_active": 1
        }
    ]

    assert is_date_paused("2026-11-09", pauses) is True
    assert is_date_paused("2026-11-10", pauses) is True
    assert is_date_paused("2026-11-11", pauses) is False

    res = build_pause_range("today", "2026-11-09")
    assert res["is_valid"]
    assert res["end_date"] == "2026-11-10"

    res = build_pause_range(
        "dates",
        "2026-11-09",
        "2026-11-09",
        "2026-11-11"
    )
    assert res["is_valid"]

    res = build_pause_range(
        "dates",
        "2026-11-09",
        "2026-11-11",
        "2026-11-09"
    )
    assert not res["is_valid"]

    assert get_effective_days([0, 1, 2, 5], [1, 2, 3]) == [1, 2]
    assert get_effective_days([0, 1, 5], None) == [0, 1, 5]

    print("OK: pause_manager работает верно!")
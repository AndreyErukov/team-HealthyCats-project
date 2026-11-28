"""Советы дня и причины пропусков из каталогов проекта."""
import json
from datetime import date
from pathlib import Path

import database


DATA_DIR = Path(__file__).parent / "data"


def _read_json(filename):
    with (DATA_DIR / filename).open("r", encoding="utf-8") as file:
        return json.load(file)


def get_reasons():
    return _read_json("miss_reasons.json")


def get_daily_tip(target_date=None):
    tips = _read_json("daily_tips.json")
    if not tips:
        return {
            "title": "Начни с малого",
            "text": "Один небольшой шаг уже имеет значение.",
            "footnote": "Меньше давления, больше заботы",
        }
    target_date = target_date or date.today()
    return tips[target_date.toordinal() % len(tips)]


def record_miss_reason(user_id, habit_id, log_date, reason):
    valid = {item["id"] for item in get_reasons()}
    if reason not in valid:
        raise ValueError("Неизвестная причина пропуска.")
    database.upsert_habit_log(user_id, habit_id, log_date, "skipped", reason)


def get_reason(reason_id):
    return next((item for item in get_reasons() if item["id"] == reason_id), None)

"""Тестовые данные интерфейса. Не заменяют бизнес-логику проекта.

Все серии, советы, календарь и рекомендации здесь — заглушки.
Дата зафиксирована по эскизам СР5 для воспроизводимой демонстрации.
"""
from copy import deepcopy
import calendar

DEMO_DATE = "2026-11-09"
DATE_LABEL = "Понедельник, 9 ноября"
USER = {"name": "Евгений"}

DAYS = [
    {"value": 0, "letter": "П", "short": "Пн", "name": "Понедельник"},
    {"value": 1, "letter": "В", "short": "Вт", "name": "Вторник"},
    {"value": 2, "letter": "С", "short": "Ср", "name": "Среда"},
    {"value": 3, "letter": "Ч", "short": "Чт", "name": "Четверг"},
    {"value": 4, "letter": "П", "short": "Пт", "name": "Пятница"},
    {"value": 5, "letter": "С", "short": "Сб", "name": "Суббота"},
    {"value": 6, "letter": "В", "short": "Вс", "name": "Воскресенье"},
]
PERIODS = [
    {"id": "morning", "label": "Утро", "icon": "sunrise", "time": "Начать с заботы о себе"},
    {"id": "day", "label": "День", "icon": "sun", "time": "Немного времени для себя"},
    {"id": "evening", "label": "Вечер", "icon": "moon", "time": "Завершить день спокойно"},
]
REASONS = [
    {"id": "time", "label": "Не хватило времени", "icon": "clock-3"},
    {"id": "forgot", "label": "Забыл(а)", "icon": "cloud"},
    {"id": "energy", "label": "Не было сил", "icon": "battery-low"},
    {"id": "plans", "label": "Изменились планы", "icon": "shuffle"},
    {"id": "hard", "label": "Слишком сложно", "icon": "mountain"},
    {"id": "other", "label": "Другая причина", "icon": "ellipsis"},
]

HABITS = [
    {
        "id": 1, "name": "Читать каждый день", "type": "useful",
        "task": "Прочитать 10 страниц", "trigger": "обеда",
        "action": "прочитаю 10 страниц", "period": "day",
        "goal": "10 страниц", "minimum": "1 страница",
        "minimum_task": "Прочитать 1 страницу", "duration": "10 минут",
        "days": [0, 1, 2, 3, 4], "is_focus": True,
        "icon": "book-open", "color": "sage", "streak": 4,
        "clean_days": 0, "replacement_plan": "",
    },
    {
        "id": 2, "name": "Стакан воды утром", "type": "useful",
        "task": "Выпить стакан воды", "trigger": "пробуждения",
        "action": "выпью стакан воды", "period": "morning",
        "goal": "1 стакан", "minimum": "Несколько глотков",
        "minimum_task": "Сделать несколько глотков воды", "duration": "2 минуты",
        "days": [0, 1, 2, 3, 4, 5, 6], "is_focus": False,
        "icon": "droplet", "color": "blue", "streak": 8,
        "clean_days": 0, "replacement_plan": "",
    },
    {
        "id": 3, "name": "Прогулка после обеда", "type": "useful",
        "task": "Прогуляться 15 минут", "trigger": "обеда",
        "action": "прогуляюсь 15 минут", "period": "day",
        "goal": "15 минут", "minimum": "5 минут",
        "minimum_task": "Прогуляться 5 минут", "duration": "15 минут",
        "days": [0, 2, 4], "is_focus": False,
        "icon": "footprints", "color": "sand", "streak": 2,
        "clean_days": 0, "replacement_plan": "",
    },
    {
        "id": 4, "name": "Выйти на свежий воздух", "type": "replacement",
        "task": "Выйти на свежий воздух", "trigger": "тяги листать ленту",
        "action": "выйду на короткую прогулку", "period": "evening",
        "goal": "5 минут на воздухе", "minimum": "1 минута у открытого окна",
        "minimum_task": "Подышать у открытого окна", "duration": "5 минут",
        "days": [0, 1, 2, 3, 4, 5, 6], "is_focus": False,
        "icon": "sprout", "color": "rose", "streak": 0,
        "clean_days": 6, "replacement_plan": "Отложить телефон и сделать короткую прогулку",
    },
]

# TODO: каталог от специалиста по данным + create_from_template.
TEMPLATES = [
    {
        "id": "reading", "title": "Читать понемногу", "description": "Одна страница уже считается", "icon": "book-open",
        "fields": {"name": "Читать каждый день", "type": "useful", "trigger": "вечернего чая", "action": "прочитаю 10 страниц", "period": "evening", "goal": "10 страниц", "minimum": "1 страница", "days": [0, 1, 2, 3, 4]},
    },
    {
        "id": "water", "title": "Начинать утро с воды", "description": "Простой ритуал после пробуждения", "icon": "droplet",
        "fields": {"name": "Стакан воды утром", "type": "useful", "trigger": "пробуждения", "action": "выпью стакан воды", "period": "morning", "goal": "1 стакан", "minimum": "Несколько глотков", "days": [0, 1, 2, 3, 4, 5, 6]},
    },
    {
        "id": "walking", "title": "Больше двигаться", "description": "Небольшая прогулка в своём темпе", "icon": "footprints",
        "fields": {"name": "Прогулка после обеда", "type": "useful", "trigger": "обеда", "action": "прогуляюсь 15 минут", "period": "day", "goal": "15 минут", "minimum": "5 минут", "days": [0, 2, 4]},
    },
]

# TODO: streak_calculator.py + statistics_heatmap.get_weekly_stats.
STATS = {"streak": 4, "longest": 9, "completed": 18, "planned": 23, "minimums": 5}
# TODO: statistics_heatmap.build_heatmap_matrix. Это НЕ история пользователя.
HEAT_LEVELS = [2, 3, 4, 1, 3, 0, 2, 4, 3, 2, 4, 4, 1, 0, 3, 2, 4, 3, 1, 2, 4, 4, 1, 3, 2, 4, 2, 1, 3, 4]
HEATMAP = [
    [{"day": day, "level": HEAT_LEVELS[day - 1] if day else 0} for day in week]
    for week in calendar.monthcalendar(2026, 11)
]


def fresh_state():
    """Только временное состояние демо, без БД и настоящих учётных записей."""
    return {
        "habits": deepcopy(HABITS),
        "logs": {2: "done", 4: "minimum"},
        "reason": "time",
        "soft_habit_id": None,
        "schedule": {"pause_active": False, "duration": "today", "start": DEMO_DATE,
                     "end": "2026-11-10", "days": [0, 1, 2, 3, 4], "reminders": True},
    }


def empty_habit():
    return {"id": None, "name": "", "type": "useful", "trigger": "", "action": "",
            "period": "day", "goal": "", "minimum": "", "days": [0, 1, 2, 3, 4],
            "is_focus": False, "replacement_plan": ""}

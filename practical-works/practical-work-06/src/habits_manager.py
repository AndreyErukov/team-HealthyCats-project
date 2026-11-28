"""Проверка формы, шаблоны и сортировка пользовательских привычек."""
import json
from copy import deepcopy
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data"
FIELD_LIMITS = {
    "name": 100,
    "trigger": 160,
    "action": 160,
    "goal": 120,
    "minimum": 120,
    "replacement_plan": 400,
}
ALLOWED_TYPES = {"useful", "replacement"}
ALLOWED_PERIODS = {"morning", "day", "evening"}
ALLOWED_ICONS = {
    "book-open", "droplet", "footprints", "sprout", "leaf", "mountain",
    "lightbulb", "cloud", "sunrise", "moon", "heart", "shield-check", "sun",
}
ALLOWED_COLORS = {"sage", "blue", "sand", "rose"}


def get_templates():
    path = DATA_DIR / "templates.json"
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, list) else []


def create_from_template(template_id):
    for template in get_templates():
        if template.get("id") == template_id:
            return deepcopy(template.get("fields", {}))
    return None


def validate_habit_form(form):
    """Возвращает (нормализованные_данные, список_ошибок)."""
    data = {field: str(form.get(field, "") or "").strip() for field in FIELD_LIMITS}
    errors = []

    for field, limit in FIELD_LIMITS.items():
        if len(data[field]) > limit:
            errors.append(f"Поле «{field}» не должно превышать {limit} символов.")

    data["type"] = str(form.get("type", "useful"))
    data["period"] = str(form.get("period", "day"))
    if data["type"] not in ALLOWED_TYPES:
        errors.append("Выбери тип привычки из предложенных вариантов.")
    if data["period"] not in ALLOWED_PERIODS:
        errors.append("Выбери время суток из предложенных вариантов.")

    required = ("name", "trigger", "action", "goal", "minimum")
    if any(not data[key] for key in required):
        errors.append("Заполни название, триггер, действие, обычный шаг и минимум.")
    if data["type"] == "replacement" and not data["replacement_plan"]:
        errors.append("Добавь мягкое действие для плана замены.")

    # days — повторяющееся поле формы. Для Flask MultiDict нужно
    # использовать getlist(), иначе сохраняется только первый checkbox.
    if hasattr(form, "getlist"):
        raw_days = form.getlist("days")
    else:
        raw_days = form.get("days", [])
    if isinstance(raw_days, str):
        raw_days = [raw_days]
    days = set()
    for value in raw_days:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= number <= 6:
            days.add(number)
    data["days"] = sorted(days)
    if not data["days"]:
        errors.append("Выбери хотя бы один день недели.")

    data["is_focus"] = str(form.get("is_focus", "")).lower() in {"on", "1", "true", "yes"}
    data["icon"] = str(form.get("icon", "") or "")
    data["color"] = str(form.get("color", "") or "")
    if data["icon"] not in ALLOWED_ICONS:
        data["icon"] = "sprout" if data["type"] == "replacement" else "leaf"
    if data["color"] not in ALLOWED_COLORS:
        data["color"] = "rose" if data["type"] == "replacement" else "sage"

    return data, errors


def filter_and_sort_habits(habits, selected="all"):
    if selected not in {"all", "useful", "replacement"}:
        selected = "all"
    items = sorted(habits, key=lambda item: (not item.get("is_focus", False), item.get("id", 0)))
    counts = {
        "all": len(items),
        "useful": sum(item.get("type") == "useful" for item in items),
        "replacement": sum(item.get("type") == "replacement" for item in items),
    }
    visible = items if selected == "all" else [h for h in items if h.get("type") == selected]
    return visible, counts


def check_habit_limit(habits, warning_threshold=5):
    """Ненавязчивое предупреждение; жёсткий лимит не включён без решения команды."""
    return len(habits) >= warning_threshold

"""Реальная статистика за календарный месяц и матрица тепловой карты."""
import calendar
from datetime import date

import database


_MONTHS = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)


def build_heatmap_matrix(user_id, year=None, month=None):
    today = date.today()
    year = year or today.year
    month = month or today.month
    last_day = calendar.monthrange(year, month)[1]
    first = date(year, month, 1).isoformat()
    last = date(year, month, last_day).isoformat()
    logs = database.get_user_logs(user_id, first, last)
    totals = {}
    for row in logs:
        if row["status"] in {"done", "minimum"}:
            totals[row["log_date"]] = totals.get(row["log_date"], 0) + 1

    weeks = []
    for week in calendar.monthcalendar(year, month):
        cells = []
        for day in week:
            if day == 0:
                cells.append({"day": 0, "level": 0, "label": ""})
            else:
                iso = date(year, month, day).isoformat()
                count = totals.get(iso, 0)
                cells.append({
                    "day": day,
                    "level": min(count, 4),
                    "count": count,
                    "date": iso,
                    "label": f"{day} {_MONTHS[month - 1].lower()} {year}: выполнено {count}",
                })
        weeks.append(cells)
    return weeks


def month_label(year, month):
    return _MONTHS[month - 1], year

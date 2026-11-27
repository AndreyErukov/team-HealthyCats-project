import json
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).parent / "berezhno.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                login TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('useful', 'replacement')),
                trigger TEXT NOT NULL,
                action TEXT NOT NULL,
                period TEXT NOT NULL CHECK(period IN ('morning', 'day', 'evening')),
                goal TEXT NOT NULL,
                minimum TEXT NOT NULL,
                days TEXT NOT NULL,
                is_focus INTEGER NOT NULL DEFAULT 0,
                replacement_plan TEXT NOT NULL DEFAULT '',
                icon TEXT NOT NULL DEFAULT 'leaf',
                color TEXT NOT NULL DEFAULT 'sage',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS habit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                log_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('done', 'minimum', 'skipped', 'relapse')),
                reason TEXT,
                UNIQUE(habit_id, log_date)
            );

            CREATE TABLE IF NOT EXISTS pauses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                work_days TEXT NOT NULL DEFAULT '[0, 1, 2, 3, 4]',
                reminders INTEGER NOT NULL DEFAULT 1
            );
        """)


def create_user(name, login, password_hash):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (name, login, password_hash)
            VALUES (?, ?, ?)
            """,
            (name, login, password_hash)
        )
        user_id = cursor.lastrowid

        conn.execute(
            "INSERT INTO user_settings (user_id) VALUES (?)",
            (user_id,)
        )

        return user_id


def get_user_by_login(login):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, name, login, password_hash
            FROM users
            WHERE login = ?
            """,
            (login,)
        ).fetchone()

        return dict(row) if row else None


def get_user_by_id(user_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, name, login, password_hash
            FROM users
            WHERE id = ?
            """,
            (user_id,)
        ).fetchone()

        return dict(row) if row else None


def get_user_habits(user_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM habits
            WHERE user_id = ? AND is_active = 1
            ORDER BY id
            """,
            (user_id,)
        ).fetchall()

        habits = []

        for row in rows:
            habit = dict(row)
            habit["days"] = json.loads(habit["days"])
            habit["is_focus"] = bool(habit["is_focus"])
            habit["task"] = habit["name"]
            habit["minimum_task"] = "Минимум: " + habit["minimum"]
            habit["duration"] = "В своём темпе"
            habits.append(habit)

        return habits


def get_habit_by_id(habit_id, user_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM habits
            WHERE id = ? AND user_id = ?
            """,
            (habit_id, user_id)
        ).fetchone()

        if row is None:
            return None

        habit = dict(row)
        habit["days"] = json.loads(habit["days"])
        habit["is_focus"] = bool(habit["is_focus"])
        habit["task"] = habit["name"]
        habit["minimum_task"] = "Минимум: " + habit["minimum"]
        habit["duration"] = "В своём темпе"

        return habit


def save_habit(user_id, form_data):
    days = form_data.get("days", [])

    if isinstance(days, str):
        days = json.loads(days)

    days = [int(day) for day in days]

    is_focus = form_data.get("is_focus", False)
    if isinstance(is_focus, str):
        is_focus = is_focus.lower() in ("1", "true", "on", "yes")

    data = (
        form_data["name"],
        form_data["type"],
        form_data["trigger"],
        form_data["action"],
        form_data["period"],
        form_data["goal"],
        form_data["minimum"],
        json.dumps(days),
        int(bool(is_focus)),
        form_data.get("replacement_plan", ""),
        form_data.get("icon", "leaf"),
        form_data.get("color", "sage"),
    )

    with get_connection() as conn:
        if bool(is_focus):
            conn.execute(
                "UPDATE habits SET is_focus = 0 WHERE user_id = ?",
                (user_id,)
            )

        habit_id = form_data.get("id")

        if habit_id:
            conn.execute(
                """
                UPDATE habits
                SET name = ?, type = ?, trigger = ?, action = ?,
                    period = ?, goal = ?, minimum = ?, days = ?,
                    is_focus = ?, replacement_plan = ?, icon = ?, color = ?
                WHERE id = ? AND user_id = ?
                """,
                data + (habit_id, user_id)
            )

            return habit_id

        cursor = conn.execute(
            """
            INSERT INTO habits (
                user_id, name, type, trigger, action, period,
                goal, minimum, days, is_focus, replacement_plan,
                icon, color
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id,) + data
        )

        return cursor.lastrowid


def upsert_habit_log(user_id, habit_id, log_date, status, reason=None):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO habit_logs (
                habit_id, user_id, log_date, status, reason
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(habit_id, log_date)
            DO UPDATE SET
                status = excluded.status,
                reason = excluded.reason
            """,
            (habit_id, user_id, log_date, status, reason)
        )


def delete_habit_log(user_id, habit_id, log_date):
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM habit_logs
            WHERE user_id = ? AND habit_id = ? AND log_date = ?
            """,
            (user_id, habit_id, log_date)
        )


def get_user_logs(user_id, start_date=None, end_date=None):
    with get_connection() as conn:
        if start_date and end_date:
            rows = conn.execute(
                """
                SELECT *
                FROM habit_logs
                WHERE user_id = ? AND log_date BETWEEN ? AND ?
                ORDER BY log_date
                """,
                (user_id, start_date, end_date)
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT *
                FROM habit_logs
                WHERE user_id = ?
                ORDER BY log_date
                """,
                (user_id,)
            ).fetchall()

        return [dict(row) for row in rows]


def get_user_schedule(user_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT work_days, reminders
            FROM user_settings
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()

        if row is None:
            return {
                "work_days": [0, 1, 2, 3, 4],
                "reminders": True
            }

        return {
            "work_days": json.loads(row["work_days"]),
            "reminders": bool(row["reminders"])
        }


def save_user_schedule(user_id, work_days, reminders):
    if isinstance(work_days, str):
        work_days = json.loads(work_days)

    work_days = [int(day) for day in work_days]

    if isinstance(reminders, str):
        reminders = reminders.lower() in ("1", "true", "on", "yes")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_settings (user_id, work_days, reminders)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                work_days = excluded.work_days,
                reminders = excluded.reminders
            """,
            (user_id, json.dumps(work_days), int(bool(reminders)))
        )


def get_user_pauses(user_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM pauses
            WHERE user_id = ?
            ORDER BY start_date
            """,
            (user_id,)
        ).fetchall()

        return [dict(row) for row in rows]


def create_pause(user_id, start_date, end_date):
    with get_connection() as conn:
        conn.execute(
            "UPDATE pauses SET is_active = 0 WHERE user_id = ?",
            (user_id,)
        )

        cursor = conn.execute(
            """
            INSERT INTO pauses (user_id, start_date, end_date, is_active)
            VALUES (?, ?, ?, 1)
            """,
            (user_id, start_date, end_date)
        )

        return cursor.lastrowid


def deactivate_pauses(user_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE pauses SET is_active = 0 WHERE user_id = ?",
            (user_id,)
        )
if __name__ == "__main__":
    init_db()

    login = "test_architect"

    user = get_user_by_login(login)

    if user is None:
        user_id = create_user(
            "Тестовый пользователь",
            login,
            "test_hash"
        )
    else:
        user_id = user["id"]

    test_habit = {
        "name": "Пить воду",
        "type": "useful",
        "trigger": "После пробуждения",
        "action": "Выпить стакан воды",
        "period": "morning",
        "goal": "Стакан воды каждое утро",
        "minimum": "Несколько глотков",
        "days": [0, 1, 2, 3, 4, 5, 6],
        "is_focus": True,
        "replacement_plan": "",
        "icon": "water",
        "color": "sage"
    }

    habit_id = save_habit(user_id, test_habit)

    print("Пользователь:", get_user_by_id(user_id))
    print("Привычки:", get_user_habits(user_id))

    upsert_habit_log(
        user_id,
        habit_id,
        "2026-11-27",
        "done"
    )

    print("Отметки:", get_user_logs(user_id))

    print("Расписание:", get_user_schedule(user_id))

    create_pause(user_id, "2026-11-27", "2026-11-29")
    print("Паузы:", get_user_pauses(user_id))

    deactivate_pauses(user_id)
    print("Пауза выключена.")

    print("OK: database.py работает!")
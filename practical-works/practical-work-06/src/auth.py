"""Регистрация, вход и проверка паролей для рабочего Flask-приложения."""
import re
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

import database


class AuthError(ValueError):
    """Ошибка проверки данных входа или регистрации."""


_LOGIN_RE = re.compile(r"^[A-Za-z0-9_.-]{3,80}$")


def register_user(name, login, password):
    name = (name or "").strip()
    login = (login or "").strip().lower()
    password = password or ""

    if not name or len(name) > 80:
        raise AuthError("Укажи имя длиной от 1 до 80 символов.")
    if not _LOGIN_RE.fullmatch(login):
        raise AuthError("Логин: от 3 до 80 символов, только латиница, цифры, точка, дефис и подчёркивание.")
    if len(password) < 8 or len(password) > 128:
        raise AuthError("Пароль должен содержать от 8 до 128 символов.")

    password_hash = generate_password_hash(password)
    try:
        return database.create_user(name, login, password_hash)
    except sqlite3.IntegrityError as exc:
        raise AuthError("Этот логин уже занят. Попробуй другой.") from exc


def authenticate_user(login, password):
    login = (login or "").strip().lower()
    password = password or ""
    if not login or not password:
        return None

    user = database.get_user_by_login(login)
    if not user:
        return None
    try:
        valid = check_password_hash(user["password_hash"], password)
    except (TypeError, ValueError):
        valid = False
    return user if valid else None

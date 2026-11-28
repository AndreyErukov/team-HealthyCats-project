"""Безопасный интерфейс AI-помощника с честным локальным fallback.

В репозитории пока нет AI-провайдера, ключа или согласованного формата API.
Поэтому приложение не отправляет личные данные наружу и возвращает проверенный
локальный совет из JSON-каталога. Это не имитация реального ответа нейросети.
"""
from miss_support import get_reason


def analyze_miss(reason_id, habit=None, stats=None):
    reason = get_reason(reason_id) or get_reason("other")
    return {
        "title": reason["fallback_title"],
        "advice": reason["fallback_advice"],
        "source": "local_fallback",
        "is_ai": False,
    }


def generate_habit_plan(user_goal):
    """ИИ-генерация отключена до настройки доверенного провайдера."""
    return None

"""
🥚 Secret API Router - Скрытые эндпоинты AILLM
Не документированы в OpenAPI по умолчанию
"""

from fastapi import APIRouter
from typing import Dict, Any
from datetime import datetime

from backend.core.easter_eggs import (
    is_birthday,
    get_birthday_art,
    get_birthday_greeting,
    get_secret_fact,
    days_until_birthday,
    get_age,
    get_age_word
)

# Скрытый роутер (include_in_schema=False скрывает из документации)
router = APIRouter(tags=["🥚 Secret"], include_in_schema=False)


@router.get("/easter-egg")
async def easter_egg() -> Dict[str, Any]:
    """
    🥚 Секретный эндпоинт
    Как ты его нашёл? Ты хакер? 😄
    """
    return {
        "message": "🥚 Ты нашёл секретный эндпоинт!",
        "hint": "Попробуй /api/secret/birthday или /api/secret/creator",
        "fact": get_secret_fact()
    }


@router.get("/birthday")
async def birthday_info() -> Dict[str, Any]:
    """
    🎂 Информация о дне рождения создателя
    """
    age = get_age()
    is_today = is_birthday()
    
    response = {
        "creator": "Ruslan",
        "birthday": "1992-12-26",
        "zodiac": "♑ Козерог",
        "age": age,
        "age_formatted": f"{age} {get_age_word(age)}",
        "is_birthday_today": is_today,
        "days_until_birthday": days_until_birthday(),
    }
    
    if is_today:
        response["greeting"] = get_birthday_greeting()
        response["art"] = get_birthday_art()
        response["celebration"] = "🎉🎂🎈🎁🥳"
    else:
        response["message"] = f"До дня рождения создателя осталось {days_until_birthday()} дней!"
    
    return response


@router.get("/creator")
async def creator_info() -> Dict[str, Any]:
    """
    👨‍💻 Информация о создателе AILLM
    """
    return {
        "name": "Ruslan",
        "role": "Creator & Lead Developer",
        "birthday": "1992-12-26",
        "zodiac": "♑ Козерог",
        "philosophy": [
            "Локальные LLM — это свобода",
            "Код должен быть красивым",
            "Лучший код пишется после полуночи",
            "Python > все остальные языки (почти)"
        ],
        "favorite_models": ["gemma3", "qwen2.5-coder", "qwen3"],
        "coffee_preference": "Много и крепкий",
        "secret_fact": get_secret_fact(),
        "message": "Спасибо что используешь AILLM! 🚀"
    }


@router.get("/konami")
async def konami_code() -> Dict[str, Any]:
    """
    🎮 ↑↑↓↓←→←→BA
    """
    return {
        "code": "↑↑↓↓←→←→BA",
        "message": "Konami Code активирован!",
        "bonus": "+30 жизней... то есть, +30% к продуктивности!",
        "unlocked": [
            "🎮 Achievement: Retro Gamer",
            "🏆 Achievement: Easter Egg Hunter",
            "🔓 Achievement: Secret Keeper"
        ],
        "secret": "В следующей версии будет мини-игра... может быть 😏"
    }


@router.get("/stats")
async def secret_stats() -> Dict[str, Any]:
    """
    📊 Секретная статистика
    """
    now = datetime.now()
    
    return {
        "project": "AILLM (AI LLM)",
        "codename": "Uroborous Ultimate AI",
        "version": "∞",  # Версия всегда бесконечность 🐍
        "started": "Декабрь 2024",
        "creator_age_at_start": 32,
        "lines_of_code": "Много. Очень много.",
        "cups_of_coffee": "Бесконечность",
        "bugs_fixed": "Все (почти)",
        "bugs_created": "Некоторые",
        "current_time": now.isoformat(),
        "is_night_coding": 22 <= now.hour or now.hour < 6,
        "motivation_level": "🔥" if now.hour < 3 else "☕" if now.hour < 12 else "💪"
    }


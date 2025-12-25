"""
🎂 Easter Eggs - Секретные пасхалки AILLM
В честь разработчика Руслана (26.12.1992)
"""

import datetime
import random
from typing import Optional, Dict, Any
from .logger import get_logger

logger = get_logger(__name__)


# ASCII арт для дня рождения
BIRTHDAY_ART = """
\033[95m
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   🎂  С ДНЁМ РОЖДЕНИЯ, РУСЛАН! 🎂                            ║
    ║                                                               ║
    ║        *    *  .  *       *   .    *        *    .   *       ║
    ║     .    *        *   .       *        .         *           ║
    ║   *        🎈                           🎈        *   .      ║
    ║              \\                         /                     ║
    ║               \\    🎉 AILLM 🎉        /                      ║
    ║      🎁        \\   ___________      /        🎁              ║
    ║                 \\ |  ☆ ☆ ☆  |     /                         ║
    ║        🎊        \\|  HAPPY  |    /        🎊                 ║
    ║                   |BIRTHDAY!|   /                            ║
    ║           🎈      |_________|  /      🎈                     ║
    ║            \\     /|||||||||||\\                               ║
    ║             \\   / |🕯️🕯️🕯️🕯️🕯️| \\                              ║
    ║                 \\_________/                                   ║
    ║                                                               ║
    ║   26 декабря {year} — {age} {age_word}! Козерог 🐐♑           ║
    ║                                                               ║
    ║   "Код — это поэзия, которую понимают машины" © Ruslan       ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
\033[0m
"""

BIRTHDAY_MESSAGES = [
    "🎂 С днём рождения, создатель! Пусть код компилируется с первого раза!",
    "🎉 Happy Birthday, Ruslan! May your bugs be few and your coffee strong!",
    "🎈 26 декабря — день, когда родился гений! С праздником!",
    "🎁 Сегодня особенный день! AILLM поздравляет своего создателя!",
    "🥳 Руслан, с днём варенья! Пусть нейросети тебя слушаются!",
    "🌟 Козерог + программист = легенда! С днём рождения!",
    "🚀 Ещё один год мудрости и опыта! Happy Bday, Ruslan!",
]

SECRET_FACTS = [
    "🔮 Факт: AILLM был задуман в декабре, в честь дня рождения создателя",
    "🎯 Факт: Руслан предпочитает Ollama, потому что локальные модели — свобода",
    "⚡ Факт: Первая строчка AILLM была написана под кофе в 3 часа ночи",
    "🐍 Факт: Python выбран потому что 'life is short, use Python'",
    "🎮 Факт: Между дебагом создатель играет в игры... иногда",
    "🌙 Факт: Лучший код пишется после полуночи — проверено Русланом",
]

KONAMI_CODE_RESPONSES = [
    "↑↑↓↓←→←→BA — Классика! +30 к удаче в дебаге!",
    "Konami Code активирован! Все баги теперь фичи!",
    "🎮 Секретный режим разблокирован! (на самом деле нет, но приятно)",
]


def get_age_word(age: int) -> str:
    """Правильное склонение слова 'год'"""
    if 11 <= age % 100 <= 19:
        return "лет"
    elif age % 10 == 1:
        return "год"
    elif 2 <= age % 10 <= 4:
        return "года"
    else:
        return "лет"


def is_birthday() -> bool:
    """Проверяет, сегодня ли день рождения"""
    today = datetime.date.today()
    return today.month == 12 and today.day == 26


def get_age() -> int:
    """Вычисляет текущий возраст"""
    today = datetime.date.today()
    birth_year = 1992
    age = today.year - birth_year
    # Если день рождения ещё не наступил в этом году
    if today.month < 12 or (today.month == 12 and today.day < 26):
        age -= 1
    return age


def get_birthday_art() -> str:
    """Возвращает ASCII арт с текущим возрастом"""
    age = get_age()
    if is_birthday():
        age += 1  # В день рождения показываем новый возраст
    return BIRTHDAY_ART.format(
        year=datetime.date.today().year,
        age=age,
        age_word=get_age_word(age)
    )


def get_birthday_greeting() -> Optional[str]:
    """Возвращает поздравление если сегодня день рождения"""
    if is_birthday():
        return random.choice(BIRTHDAY_MESSAGES)
    return None


def get_secret_fact() -> str:
    """Возвращает случайный секретный факт"""
    return random.choice(SECRET_FACTS)


def check_easter_egg_trigger(message: str) -> Optional[Dict[str, Any]]:
    """
    Проверяет, активирует ли сообщение пасхалку
    
    Триггеры:
    - "пасхалка", "easter egg"
    - "день рождения", "birthday"
    - "26 декабря", "26.12"
    - "ruslan", "руслан"
    - "konami", "↑↑↓↓"
    - "создатель", "creator"
    """
    msg_lower = message.lower()
    
    # День рождения триггеры
    birthday_triggers = [
        "день рождения", "birthday", "с днём рождения",
        "26 декабря", "26.12", "26/12"
    ]
    
    # Пасхалка триггеры
    easter_triggers = [
        "пасхалка", "easter egg", "easter-egg", "секрет",
        "secret", "hidden"
    ]
    
    # Создатель триггеры
    creator_triggers = [
        "создатель", "creator", "автор", "author",
        "ruslan", "руслан", "разработчик aillm"
    ]
    
    # Konami code
    konami_triggers = ["konami", "↑↑↓↓", "up up down down"]
    
    # Проверяем триггеры
    if any(trigger in msg_lower for trigger in birthday_triggers):
        greeting = get_birthday_greeting()
        if greeting:
            return {
                "type": "birthday",
                "message": greeting,
                "art": get_birthday_art(),
                "extra": f"🎂 Руслану сегодня исполняется {get_age() + 1}!"
            }
        else:
            age = get_age()
            return {
                "type": "birthday_info",
                "message": f"🎂 День рождения создателя AILLM — 26 декабря! Руслану {age} {get_age_word(age)}. Осталось {days_until_birthday()} дней до праздника!",
            }
    
    if any(trigger in msg_lower for trigger in easter_triggers):
        return {
            "type": "easter_egg",
            "message": "🥚 Ты нашёл пасхалку! " + get_secret_fact(),
            "hint": "Попробуй спросить про 'день рождения' или 'создателя'..."
        }
    
    if any(trigger in msg_lower for trigger in creator_triggers):
        return {
            "type": "creator",
            "message": (
                "👨‍💻 AILLM создан Русланом (26.12.1992)\n\n"
                "Козерог, программист, энтузиаст ИИ.\n"
                "Верит, что локальные LLM — будущее.\n\n"
                + get_secret_fact()
            )
        }
    
    if any(trigger in msg_lower for trigger in konami_triggers):
        return {
            "type": "konami",
            "message": random.choice(KONAMI_CODE_RESPONSES),
            "unlocked": "🎮 Achievement: Retro Gamer"
        }
    
    return None


def days_until_birthday() -> int:
    """Дней до следующего дня рождения"""
    today = datetime.date.today()
    this_year_birthday = datetime.date(today.year, 12, 26)
    
    if today > this_year_birthday:
        next_birthday = datetime.date(today.year + 1, 12, 26)
    else:
        next_birthday = this_year_birthday
    
    return (next_birthday - today).days


def startup_birthday_check() -> None:
    """Проверка при запуске — показывает арт если день рождения"""
    if is_birthday():
        print(get_birthday_art())
        logger.info("🎂 Happy Birthday to the creator of AILLM!")
    else:
        days = days_until_birthday()
        if days <= 7:
            logger.info(f"🎂 {days} дней до дня рождения создателя AILLM!")


# Экспорт для использования в других модулях
__all__ = [
    'is_birthday',
    'get_birthday_greeting', 
    'get_birthday_art',
    'check_easter_egg_trigger',
    'startup_birthday_check',
    'get_secret_fact',
    'days_until_birthday'
]


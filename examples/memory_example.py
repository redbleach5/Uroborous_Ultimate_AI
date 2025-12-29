#!/usr/bin/env python3
"""
Пример использования LongTermMemory для:
- Персонализации ответов
- Избежания повторных ошибок  
- Рекомендаций моделей

Запуск: python examples/memory_example.py
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к backend
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.memory.long_term import LongTermMemory
from backend.config import MemoryConfig


async def demo_user_preferences(memory: LongTermMemory):
    """Демонстрация работы с предпочтениями пользователя"""
    print("\n" + "=" * 60)
    print("🎨 ПЕРСОНАЛИЗАЦИЯ - User Preferences")
    print("=" * 60)
    
    # Установка предпочтений
    await memory.save_user_preference("language", "ru")
    await memory.save_user_preference("code_style", "pythonic")
    await memory.save_user_preference("detail_level", "detailed")
    await memory.save_user_preference("preferred_frameworks", ["fastapi", "pydantic", "pytest"])
    await memory.save_user_preference("response_format", "markdown")
    
    print("✅ Сохранены предпочтения:")
    
    # Получение всех предпочтений
    prefs = await memory.get_all_user_preferences()
    for key, value in prefs.items():
        print(f"   {key}: {value}")
    
    # Получение персонализированного промпта
    prompt = await memory.get_personalization_prompt()
    print("\n📝 Сгенерированный промпт для агента:")
    print(prompt)


async def demo_failed_tasks(memory: LongTermMemory):
    """Демонстрация работы с failed tasks для избежания ошибок"""
    print("\n" + "=" * 60)
    print("⚠️ ИЗБЕЖАНИЕ ОШИБОК - Failed Tasks Tracking")
    print("=" * 60)
    
    # Сохранение неудачных задач
    await memory.save_failed_task(
        task="Создать REST API для управления пользователями с JWT аутентификацией",
        agent="code_writer",
        error_type="SyntaxError",
        error_message="Отсутствует импорт jwt модуля",
        error_context={"file": "api/auth.py", "line": 15}
    )
    
    await memory.save_failed_task(
        task="Написать unit тесты для API аутентификации",
        agent="code_writer", 
        error_type="ImportError",
        error_message="Модуль pytest-asyncio не установлен",
        error_context={"suggestion": "pip install pytest-asyncio"}
    )
    
    print("✅ Сохранены failed задачи")
    
    # Поиск похожих ошибок
    similar_task = "Создать API аутентификации с токенами"
    warnings = await memory.get_error_avoidance_prompt(similar_task, agent="code_writer")
    
    print(f"\n🔍 Поиск предупреждений для задачи: '{similar_task}'")
    if warnings:
        print(warnings)
    else:
        print("   Нет похожих ошибок в истории")


async def demo_model_recommendations(memory: LongTermMemory):
    """Демонстрация рекомендаций моделей на основе истории"""
    print("\n" + "=" * 60)
    print("🤖 РЕКОМЕНДАЦИИ МОДЕЛЕЙ - Model Task Performance")
    print("=" * 60)
    
    # Записываем производительность моделей
    test_data = [
        ("qwen2.5-coder:7b", "code", True, 85.0, 2.5),
        ("qwen2.5-coder:7b", "code", True, 90.0, 2.3),
        ("qwen2.5-coder:7b", "code", True, 88.0, 2.4),
        ("llama3.2:3b", "code", True, 70.0, 1.5),
        ("llama3.2:3b", "code", False, 0.0, 3.0),
        ("llama3.2:3b", "chat", True, 85.0, 1.2),
        ("llama3.2:3b", "chat", True, 88.0, 1.1),
        ("llama3.2:3b", "chat", True, 90.0, 1.0),
        ("gemma2:9b", "analysis", True, 92.0, 3.5),
        ("gemma2:9b", "analysis", True, 88.0, 3.8),
        ("deepseek-r1:14b", "reasoning", True, 95.0, 5.0),
        ("deepseek-r1:14b", "reasoning", True, 93.0, 4.8),
    ]
    
    for model, task_type, success, quality, duration in test_data:
        await memory.record_model_task_performance(
            model_name=model,
            task_type=task_type,
            success=success,
            quality=quality,
            duration=duration
        )
    
    print("✅ Записана производительность моделей")
    
    # Получаем рекомендации
    recommendations = await memory.get_model_task_recommendations()
    
    print("\n📊 Рекомендации моделей по типам задач:")
    for task_type, model in recommendations.items():
        print(f"   {task_type:12} → {model}")
    
    # Детальная информация для конкретного типа
    print("\n🔍 Детали для task_type='code':")
    best = await memory.get_best_model_for_task_type("code")
    if best:
        print(f"   Модель: {best['model_name']}")
        print(f"   Success rate: {best['success_rate']:.0%}")
        print(f"   Avg quality: {best['avg_quality']:.1f}")
        print(f"   Avg duration: {best['avg_duration']:.2f}s")
        print(f"   Total samples: {best['total_samples']}")


async def demo_memory_stats(memory: LongTermMemory):
    """Демонстрация статистики памяти"""
    print("\n" + "=" * 60)
    print("📈 СТАТИСТИКА ПАМЯТИ")
    print("=" * 60)
    
    stats = await memory.get_learning_stats()
    
    print(f"   Total memories: {stats['total_memories']}")
    print(f"   With feedback: {stats['with_feedback']}")
    print(f"   Avg quality: {stats['avg_quality']}")
    print(f"   Helpful rate: {stats['helpful_rate']}%")
    print(f"   Failed tasks: {stats['failed_tasks_count']}")
    print(f"   User preferences: {stats['user_preferences_count']}")


async def main():
    """Основная функция примера"""
    print("🧠 Пример работы с LongTermMemory")
    print("=" * 60)
    
    # Создаем конфигурацию памяти
    config = MemoryConfig(
        storage_path="memory/example_memories.db",
        max_memories=1000,
        similarity_threshold=0.7
    )
    
    # Инициализируем память
    memory = LongTermMemory(config)
    await memory.initialize()
    
    try:
        # Демонстрация функций
        await demo_user_preferences(memory)
        await demo_failed_tasks(memory)
        await demo_model_recommendations(memory)
        await demo_memory_stats(memory)
        
        print("\n" + "=" * 60)
        print("✅ Все демонстрации завершены успешно!")
        print("=" * 60)
        
    finally:
        await memory.shutdown()
        
        # Удаляем тестовую базу
        import os
        try:
            os.remove("memory/example_memories.db")
            print("\n🧹 Тестовая база данных удалена")
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    asyncio.run(main())


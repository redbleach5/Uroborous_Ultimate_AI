"""
Chat router - Простой универсальный чат без агентов
Для быстрых ответов, шуток, новостей, команд Linux и т.д.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

from backend.core.logger import get_logger
from backend.llm.base import LLMMessage

logger = get_logger(__name__)

router = APIRouter()


class ChatMessage(BaseModel):
    role: str  # "user" или "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None
    mode: Optional[str] = "general"  # general, ide, research
    context: Optional[Dict[str, Any]] = None
    model: Optional[str] = None  # Выбранная модель (None = автовыбор)
    provider: Optional[str] = None  # Выбранный провайдер


class ChatResponse(BaseModel):
    success: bool
    message: str
    error: Optional[str] = None
    warning: Optional[str] = None  # Предупреждение о сложности
    metadata: Optional[Dict[str, Any]] = None


# Системные промпты для разных режимов
SYSTEM_PROMPTS = {
    "general": """Ты — универсальный AI-ассистент. Ты можешь:
- Отвечать на любые вопросы
- Шутить и поддерживать непринуждённую беседу
- Объяснять команды Linux, технологии, концепции
- Помогать с повседневными задачами
- Давать советы и рекомендации

ВАЖНЫЕ ПРАВИЛА:
1. Отвечай ТОЛЬКО на русском языке. Не используй слова из других языков (вьетнамского, хинди, итальянского и т.д.)
2. Если пользователь спрашивает о новостях или актуальных событиях:
   - Если тебе предоставлен веб-контекст с реальными данными — используй его
   - Если веб-контекста НЕТ — честно скажи: "У меня нет доступа к актуальным новостям. Мои знания ограничены датой обучения модели."
   - НИКОГДА не выдумывай новости, события или факты!
3. Если не знаешь ответ — так и скажи, не придумывай информацию.

Будь дружелюбным и полезным. Используй эмодзи где уместно.
Форматируй ответы с markdown для лучшей читаемости.
Текущая дата: {current_date}""",

    "ide": """Ты — опытный программист и разработчик. Ты можешь:
- Писать и анализировать код на любых языках
- Отлаживать и исправлять ошибки
- Объяснять архитектуру и паттерны проектирования
- Оптимизировать производительность кода
- Ревьюить код и предлагать улучшения
- Помогать с Git, Docker, CI/CD и DevOps

Отвечай технически грамотно, с примерами кода когда уместно.
Используй markdown с подсветкой синтаксиса для кода.
Будь конкретен и точен в технических деталях.""",

    "research": """Ты — эксперт-исследователь и аналитик. Ты можешь:
- Глубоко анализировать темы и предоставлять исследования
- Сравнивать технологии и подходы
- Искать и обобщать информацию
- Создавать структурированные отчёты
- Анализировать тренды и прогнозировать развитие

Предоставляй детальные, хорошо структурированные ответы.
Указывай источники информации где возможно.
Используй таблицы, списки и другое форматирование для наглядности."""
}


def get_system_prompt(mode: str) -> str:
    """Получает системный промпт для режима с подстановкой даты"""
    prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["general"])
    current_date = datetime.now().strftime("%d %B %Y, %H:%M")
    return prompt.format(current_date=current_date)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, chat_request: ChatRequest):
    """
    Простой чат без агентов — напрямую через LLM.
    Быстрые ответы для повседневных вопросов.
    НЕ блокирует сложные операции — только предупреждает пользователя.
    """
    logger.info(f"Chat request: mode={chat_request.mode}, message_length={len(chat_request.message)}")
    
    engine = request.app.state.engine
    
    if not engine:
        raise HTTPException(status_code=503, detail="Движок не инициализирован")
    
    llm_manager = engine.llm_manager
    
    if not llm_manager:
        raise HTTPException(status_code=503, detail="LLM провайдер не доступен")
    
    # Анализируем сложность задачи (НЕ блокирует выполнение!)
    complexity_warning = None
    complexity_info = None
    try:
        from backend.core.complexity_analyzer import get_complexity_analyzer
        analyzer = get_complexity_analyzer()
        complexity_info = analyzer.analyze(
            task=chat_request.message,
            model=chat_request.model,
            task_type=chat_request.mode
        )
        
        if complexity_info.should_warn:
            complexity_warning = complexity_info.warning_message
            logger.info(f"Chat complexity warning: {complexity_info.level.value}, ~{complexity_info.estimated_minutes:.1f} min")
    except Exception as e:
        logger.debug(f"Complexity analysis failed (non-critical): {e}")
    
    try:
        # Формируем сообщения
        messages = [
            LLMMessage(
                role="system",
                content=get_system_prompt(chat_request.mode or "general")
            )
        ]
        
        # Добавляем историю если есть
        if chat_request.history:
            for msg in chat_request.history[-10:]:  # Последние 10 сообщений
                messages.append(LLMMessage(
                    role=msg.role,
                    content=msg.content
                ))
        
        # Добавляем текущее сообщение
        messages.append(LLMMessage(
            role="user",
            content=chat_request.message
        ))
        
        # Определяем нужен ли поиск в интернете
        needs_search = any(keyword in chat_request.message.lower() for keyword in [
            "новости", "news", "последние", "актуальные", "сегодня",
            "цены", "курс", "погода", "события"
        ])
        
        web_context = ""
        if needs_search and engine.tool_registry:
            try:
                logger.info("Chat: Performing web search for context")
                search_result = await engine.tool_registry.execute_tool(
                    "web_search",
                    {"query": chat_request.message, "max_results": 5}
                )
                
                if search_result.success and search_result.result:
                    results = search_result.result.get("results", [])
                    if results:
                        web_context = "\n\n📰 **Найденная информация из интернета:**\n"
                        for i, result in enumerate(results[:3], 1):
                            title = result.get('title', '').strip()
                            snippet = result.get('snippet', '').strip()
                            url = result.get('url', '').strip()
                            web_context += f"\n{i}. **{title}**\n{snippet}\n[Источник]({url})\n"
                        
                        # Добавляем контекст к сообщению
                        messages[-1] = LLMMessage(
                            role="user",
                            content=f"{chat_request.message}\n\n{web_context}\n\nИспользуй эту информацию для ответа."
                        )
            except Exception as e:
                logger.warning(f"Chat web search failed: {e}")
        
        # ======= РАСПРЕДЕЛЁННЫЙ УМНЫЙ ВЫБОР МОДЕЛИ =======
        # Учитывает все сервера (localhost + remote) и выбирает лучший
        model_to_use = chat_request.model
        provider_to_use = chat_request.provider
        server_url_to_use = None  # URL сервера где есть модель
        used_distributed = False
        
        # Если модель НЕ указана явно, выбираем автоматически с учётом всех серверов
        if not model_to_use:
            try:
                from backend.core.resource_aware_selector import ResourceAwareSelector
                
                # Получаем селектор из engine или создаём
                resource_selector = getattr(engine, 'resource_aware_selector', None)
                if not resource_selector:
                    config = getattr(engine, 'raw_config', {})
                    resource_selector = ResourceAwareSelector(llm_manager, config)
                
                # Определяем тип задачи для чата
                task_type = "chat" if chat_request.mode == "general" else chat_request.mode
                complexity_level = complexity_info.level.value if complexity_info else "simple"
                quality = "fast" if complexity_level in ["trivial", "simple"] else "balanced"
                
                # Распределённый выбор: ищет модель на ВСЕХ доступных серверах
                selection = await resource_selector.select_adaptive_model(
                    task=chat_request.message,
                    task_type=task_type,
                    complexity=complexity_level,
                    quality_requirement=quality,
                    preferred_model=chat_request.model
                )
                
                model_to_use = selection.model
                used_distributed = selection.used_distributed_routing
                
                # Если распределённый роутинг нашёл модель на другом сервере
                if selection.server_url:
                    server_url_to_use = selection.server_url
                    logger.info(
                        f"Chat: Distributed routing -> {model_to_use} @ {selection.server_name or selection.server_url}"
                    )
                else:
                    logger.info(f"Chat: Local selection -> {model_to_use}")
                    
            except Exception as e:
                logger.warning(f"Smart selection failed, using fallback: {e}")
                # Fallback на старую логику
                if complexity_info and complexity_info.level.value in ["trivial", "simple"]:
                    ollama_provider = llm_manager.providers.get("ollama")
                    if ollama_provider:
                        fast_models = ollama_provider.recommended_models.get("fast", [])
                        available = getattr(ollama_provider, '_available_models', [])
                        for fast_model in fast_models:
                            if any(fast_model in m for m in available):
                                model_to_use = next((m for m in available if fast_model in m), None)
                                if model_to_use:
                                    break
        
        # Если указана модель явно или выбрали автоматически
        original_model = None
        original_base_url = None
        if model_to_use:
            ollama_provider = llm_manager.providers.get("ollama")
            if ollama_provider:
                # Временно меняем модель по умолчанию
                original_model = ollama_provider.default_model
                ollama_provider.default_model = model_to_use
                
                # Если нужно использовать другой сервер
                if server_url_to_use and hasattr(ollama_provider, 'client'):
                    original_base_url = ollama_provider.base_url
                    ollama_provider.base_url = server_url_to_use
                    # Пересоздаём клиент с новым URL
                    import httpx
                    ollama_provider.client = httpx.AsyncClient(
                        base_url=server_url_to_use,
                        timeout=ollama_provider.timeout
                    )
                    logger.info(f"Chat: Switched to server {server_url_to_use}")
                
                logger.info(f"Chat: Using model: {model_to_use}")
        
        # Генерируем ответ
        response = await llm_manager.generate(
            messages=messages,
            provider_name=provider_to_use,
            model=model_to_use,
            temperature=0.7,
            max_tokens=2000
        )
        
        # Восстанавливаем оригинальную модель и сервер если меняли
        if model_to_use:
            ollama_provider = llm_manager.providers.get("ollama")
            if ollama_provider:
                if original_model:
                    ollama_provider.default_model = original_model
                # Восстанавливаем оригинальный сервер если меняли
                if original_base_url:
                    ollama_provider.base_url = original_base_url
                    import httpx
                    ollama_provider.client = httpx.AsyncClient(
                        base_url=original_base_url,
                        timeout=ollama_provider.timeout
                    )
        
        # Определяем, была ли использована быстрая модель
        used_fast_model = (
            complexity_info and 
            complexity_info.level.value in ["trivial", "simple"] and
            response.model and
            any(x in response.model.lower() for x in ["1b", "1.5b", "2b"])
        )
        
        return ChatResponse(
            success=True,
            message=response.content,
            warning=complexity_warning,  # Предупреждение о сложности (если было)
            metadata={
                "model": response.model,
                "provider": getattr(response, 'provider', 'ollama'),
                "mode": chat_request.mode,
                "has_thinking": getattr(response, 'thinking', None) is not None,
                "thinking": getattr(response, 'thinking', None),
                "web_search_used": bool(web_context),
                "complexity_level": complexity_info.level.value if complexity_info else None,
                "estimated_minutes": complexity_info.estimated_minutes if complexity_info else None,
                "smart_model_selection": True,  # Показываем что использовался умный выбор
                "used_fast_model": used_fast_model,  # Была ли использована быстрая модель
                "distributed_routing": used_distributed,  # Была ли распределённая маршрутизация
                "server_used": server_url_to_use  # Какой сервер использовался
            }
        )
        
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        error_message = str(e)
        
        if "timeout" in error_message.lower():
            error_message = "Превышено время ожидания. Попробуйте ещё раз."
        elif "connection" in error_message.lower():
            error_message = "Ошибка подключения к LLM. Проверьте настройки."
        
        return ChatResponse(
            success=False,
            message="",
            error=error_message
        )


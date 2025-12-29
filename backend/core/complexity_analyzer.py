"""
Complexity Analyzer - Анализ сложности задач и генерация предупреждений
НЕ блокирует выполнение, только предупреждает пользователя

Динамически учитывает доступные ресурсы (GPU, CPU, память)
"""

import re
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from .logger import get_logger
from .types import ComplexityLevel

logger = get_logger(__name__)


@dataclass
class ComplexityEstimate:
    """Результат анализа сложности (специфичный для этого модуля)"""
    level: ComplexityLevel
    estimated_minutes: float
    warning_message: Optional[str]
    should_warn: bool
    factors: Dict[str, Any]


class ComplexityAnalyzer:
    """
    Анализатор сложности задач с динамическим учётом ресурсов
    
    Важно: НЕ блокирует выполнение!
    Только генерирует предупреждения для пользователя.
    
    Динамически учитывает:
    - Количество и мощность GPU
    - Доступную память
    - Текущую загрузку системы
    """
    
    # Ключевые слова для определения типа задачи
    COMPLEX_KEYWORDS = {
        "extreme": [
            "создай полное приложение", "create full application",
            "напиши полную систему", "build complete system",
            "разработай платформу", "develop platform",
            "создай игру с нуля", "create game from scratch",
            "напиши фреймворк", "write framework",
            "создай IDE", "build IDE",
            "разработай CRM", "develop CRM",
            "создай интернет-магазин", "create e-commerce",
        ],
        "very_complex": [
            "напиши систему", "write system",
            "создай приложение", "create application",
            "разработай API", "develop API",
            "создай бота", "create bot",
            "напиши парсер", "write parser",
            "создай dashboard", "create dashboard",
            "напиши тесты для всего", "write all tests",
        ],
        "complex": [
            "напиши класс", "write class",
            "создай модуль", "create module",
            "рефакторинг", "refactor",
            "оптимизируй", "optimize",
            "интегрируй", "integrate",
            "добавь функционал", "add functionality",
            "исправь все ошибки", "fix all errors",
        ],
        "moderate": [
            "напиши функцию", "write function",
            "объясни код", "explain code",
            "проанализируй", "analyze",
            "сравни", "compare",
            "исследуй", "research",
        ]
    }
    
    # Паттерны для определения сложности
    CODE_PATTERNS = [
        (r'\bигр[уа]', 5.0),  # игра
        (r'\bприложени[еяй]', 4.0),  # приложение
        (r'\bсистем[уа]', 4.0),  # система
        (r'\bфреймворк', 5.0),  # фреймворк
        (r'\bплатформ[уа]', 5.0),  # платформа
        (r'\bAPI\b', 3.0),
        (r'\bбот[а]?\b', 3.0),  # бот
        (r'\bкласс[а]?\b', 2.0),  # класс
        (r'\bфункци[юя]', 1.5),  # функция
        (r'\bscript\b', 1.5),
        (r'\bmodule\b', 2.0),
        (r'\bмодул[ья]', 2.0),  # модуль
    ]
    
    def __init__(self):
        self.default_time_estimates = {
            ComplexityLevel.TRIVIAL: 0.1,      # 6 секунд
            ComplexityLevel.SIMPLE: 0.5,       # 30 секунд
            ComplexityLevel.MODERATE: 2.0,     # 2 минуты
            ComplexityLevel.COMPLEX: 8.0,      # 8 минут
            ComplexityLevel.VERY_COMPLEX: 20.0,  # 20 минут
            ComplexityLevel.EXTREME: 45.0,     # 45 минут
        }
        
        # Кэш информации о ресурсах
        self._resource_info_cache: Optional[Dict[str, Any]] = None
        self._resource_cache_time: float = 0
        self._resource_cache_ttl: float = 60.0  # Кэш на 1 минуту
        self._last_ollama_url: Optional[str] = None  # Для отслеживания смены сервера
    
    def _get_resource_info_sync(self) -> Dict[str, Any]:
        """
        Синхронно получает информацию о ресурсах (с кэшированием)
        
        Учитывает как локальные ресурсы, так и УДАЛЁННЫЙ Ollama сервер!
        """
        import time
        current_time = time.time()
        
        # Получаем текущий URL Ollama (может измениться!)
        current_ollama_url = self._get_ollama_url()
        
        # Проверяем кэш (сбрасываем если сменился сервер)
        cache_valid = (
            self._resource_info_cache and 
            current_time - self._resource_cache_time < self._resource_cache_ttl and
            self._last_ollama_url == current_ollama_url  # URL не изменился
        )
        
        if cache_valid:
            return self._resource_info_cache
        
        # Запоминаем текущий URL
        self._last_ollama_url = current_ollama_url
        
        resource_info = {
            "gpu_count": 0,
            "gpu_memory_gb": 0,
            "total_gpu_memory_gb": 0,
            "cpu_cores": 4,
            "ram_gb": 8,
            "resource_level": "medium",
            "ollama_remote": False,
            "ollama_url": None
        }
        
        # 1. Сначала пробуем получить информацию от Ollama сервера
        ollama_info = self._get_ollama_server_info()
        if ollama_info:
            resource_info.update(ollama_info)
            logger.debug(f"Using Ollama server resources: {ollama_info}")
        else:
            # 2. Fallback на локальные ресурсы (если Ollama локальный)
            local_info = self._get_local_gpu_info()
            resource_info.update(local_info)
        
        # Получаем информацию о CPU (локально, для бэкенда)
        try:
            import os
            resource_info["cpu_cores"] = os.cpu_count() or 4
        except (OSError, AttributeError):
            pass
        
        # Получаем информацию о RAM (локально)
        try:
            import psutil
            resource_info["ram_gb"] = psutil.virtual_memory().total / (1024**3)
        except (ImportError, AttributeError, OSError):
            pass
        
        # Определяем уровень ресурсов на основе GPU
        resource_info["resource_level"] = self._determine_resource_level(
            resource_info["total_gpu_memory_gb"],
            resource_info["gpu_count"]
        )
        
        # Кэшируем результат
        self._resource_info_cache = resource_info
        self._resource_cache_time = current_time
        
        return resource_info
    
    def _get_ollama_server_info(self) -> Optional[Dict[str, Any]]:
        """
        Получает информацию о ресурсах от Ollama сервера
        Работает как с локальным, так и с удалённым сервером (например 192.168.178.126:11434)
        """
        import urllib.request
        import json
        
        # Пытаемся получить URL Ollama из конфига
        ollama_url = self._get_ollama_url()
        if not ollama_url:
            return None
        
        try:
            # Ollama API: /api/ps показывает запущенные модели и использование памяти
            ps_url = f"{ollama_url}/api/ps"
            
            req = urllib.request.Request(ps_url, method='GET')
            req.add_header('Content-Type', 'application/json')
            
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            # Анализируем запущенные модели для оценки ресурсов
            data.get('models', [])
            
            # Также получаем список всех доступных моделей для оценки мощности
            tags_url = f"{ollama_url}/api/tags"
            req = urllib.request.Request(tags_url, method='GET')
            
            with urllib.request.urlopen(req, timeout=3) as response:
                tags_data = json.loads(response.read().decode('utf-8'))
            
            available_models = tags_data.get('models', [])
            
            # Оцениваем ресурсы сервера по доступным моделям
            resource_estimate = self._estimate_resources_from_models(available_models)
            resource_estimate["ollama_remote"] = not ollama_url.startswith("http://localhost") and not ollama_url.startswith("http://127.0.0.1")
            resource_estimate["ollama_url"] = ollama_url
            resource_estimate["available_models_count"] = len(available_models)
            
            logger.info(
                f"Ollama server ({ollama_url}): "
                f"~{resource_estimate['total_gpu_memory_gb']:.0f} GB VRAM estimated, "
                f"{len(available_models)} models available"
            )
            
            return resource_estimate
            
        except Exception as e:
            logger.debug(f"Failed to get Ollama server info from {ollama_url}: {e}")
            return None
    
    def _get_ollama_url(self) -> Optional[str]:
        """
        Получает URL Ollama сервера с поддержкой динамических IP
        
        Приоритет:
        1. Переменная окружения OLLAMA_HOST
        2. Конфигурационный файл config.yaml
        3. Авто-обнаружение в локальной сети (если включено)
        4. Fallback на localhost:11434
        
        Поддерживает:
        - IP адреса: 192.168.178.126
        - Hostnames: ollama-server, ollama-server.local
        - mDNS: ollama.local (Bonjour/Avahi)
        """
        import os
        
        # 1. Проверяем переменные окружения (высший приоритет)
        env_url = os.environ.get('OLLAMA_HOST') or os.environ.get('OLLAMA_BASE_URL')
        if env_url:
            resolved_url = self._resolve_ollama_url(env_url)
            if resolved_url:
                logger.debug(f"Using Ollama URL from environment: {resolved_url}")
                return resolved_url
        
        # 2. Пробуем загрузить из конфига
        try:
            import yaml
            
            config_paths = [
                os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml'),
                'backend/config/config.yaml',
                'config/config.yaml'
            ]
            
            for config_path in config_paths:
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        ollama_config = config.get('llm', {}).get('providers', {}).get('ollama', {})
                        
                        # Проверяем основной URL
                        if ollama_config.get('base_url'):
                            resolved_url = self._resolve_ollama_url(ollama_config['base_url'])
                            if resolved_url:
                                logger.debug(f"Using Ollama URL from config: {resolved_url}")
                                return resolved_url
                        
                        # Проверяем fallback URLs (для динамических IP)
                        fallback_urls = ollama_config.get('fallback_urls', [])
                        for fallback in fallback_urls:
                            resolved = self._resolve_ollama_url(fallback)
                            if resolved:
                                logger.info(f"Primary Ollama unavailable, using fallback: {resolved}")
                                return resolved
                        
                        # Пробуем авто-обнаружение если включено
                        if ollama_config.get('auto_discover', False):
                            discovered = self._auto_discover_ollama()
                            if discovered:
                                logger.info(f"Auto-discovered Ollama server: {discovered}")
                                return discovered
            
        except Exception as e:
            logger.debug(f"Failed to load Ollama URL from config: {e}")
        
        # 3. Fallback на localhost
        logger.debug("Using default Ollama URL: http://localhost:11434")
        return "http://localhost:11434"
    
    def _resolve_ollama_url(self, url: str) -> Optional[str]:
        """
        Резолвит и проверяет доступность Ollama URL
        Поддерживает hostnames, IP, mDNS
        
        Args:
            url: URL или hostname (например "ollama-server" или "192.168.178.126")
            
        Returns:
            Рабочий URL или None если недоступен
        """
        import socket
        import urllib.request
        
        # Нормализуем URL
        if not url.startswith('http'):
            url = f"http://{url}"
        if ':' not in url.split('://')[-1].split('/')[0]:
            # Нет порта в хосте
            url = url.rstrip('/') + ':11434'
        
        try:
            # Извлекаем hostname для резолва
            from urllib.parse import urlparse
            parsed = urlparse(url)
            hostname = parsed.hostname
            port = parsed.port or 11434
            
            # Пробуем разрезолвить hostname (поддержка DNS/mDNS)
            try:
                ip = socket.gethostbyname(hostname)
                logger.debug(f"Resolved {hostname} -> {ip}")
            except socket.gaierror:
                # Не удалось разрезолвить - возможно hostname недоступен
                logger.debug(f"Failed to resolve hostname: {hostname}")
                return None
            
            # Проверяем доступность Ollama API (быстрая проверка)
            test_url = f"http://{ip}:{port}/api/tags"
            req = urllib.request.Request(test_url, method='GET')
            
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    # Возвращаем URL с оригинальным hostname (для читаемости логов)
                    return f"http://{hostname}:{port}"
                    
        except Exception as e:
            logger.debug(f"Ollama not available at {url}: {e}")
            return None
        
        return None
    
    def _auto_discover_ollama(self) -> Optional[str]:
        """
        Автоматическое обнаружение Ollama сервера в локальной сети
        
        Пробует:
        1. mDNS имена (ollama.local, ollama-server.local)
        2. Общие hostnames (ollama, ollama-server)
        3. Сканирование популярных IP в подсети
        """
        import socket
        
        # Список возможных hostnames для Ollama
        hostnames_to_try = [
            'ollama.local',           # mDNS (macOS/Linux с Avahi)
            'ollama-server.local',    # mDNS альтернатива
            'ollama',                 # Простой hostname
            'ollama-server',          # Альтернатива
        ]
        
        # Пробуем известные hostnames
        for hostname in hostnames_to_try:
            url = self._resolve_ollama_url(hostname)
            if url:
                return url
        
        # Пробуем найти в локальной подсети (192.168.x.x)
        try:
            # Получаем локальный IP для определения подсети
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            
            # Извлекаем подсеть
            subnet = '.'.join(local_ip.split('.')[:-1])
            
            # Проверяем популярные IP (1, 100, 126, 200, 254)
            popular_ips = [1, 100, 126, 200, 254]
            
            for last_octet in popular_ips:
                test_ip = f"{subnet}.{last_octet}"
                if test_ip == local_ip:
                    continue  # Пропускаем себя
                
                url = self._resolve_ollama_url(test_ip)
                if url:
                    logger.info(f"Auto-discovered Ollama at {test_ip}")
                    return url
                    
        except Exception as e:
            logger.debug(f"Auto-discovery failed: {e}")
        
        return None
    
    def set_ollama_url(self, url: str) -> None:
        """
        Программно устанавливает URL Ollama сервера
        Полезно для динамического переключения между серверами
        
        Args:
            url: URL Ollama сервера (например "http://192.168.178.126:11434")
        """
        import os
        os.environ['OLLAMA_BASE_URL'] = url
        # Сбрасываем кэш ресурсов чтобы подхватить новый сервер
        self._resource_info_cache = None
        self._resource_cache_time = 0
        logger.info(f"Ollama URL updated to: {url}")
    
    def _estimate_resources_from_models(self, models: list) -> Dict[str, Any]:
        """
        Оценивает ресурсы сервера по доступным моделям
        
        Логика: если сервер может запустить 70B модель = много VRAM
        """
        resource_info = {
            "gpu_count": 1,
            "gpu_memory_gb": 24,
            "total_gpu_memory_gb": 24
        }
        
        # Ищем самую большую доступную модель
        max_model_size = 0
        
        for model in models:
            model_name = model.get('name', '').lower()
            model.get('size', 0)  # Размер в байтах
            
            # Определяем размер модели по названию
            if any(x in model_name for x in ['70b', '72b', '65b', '67b']):
                max_model_size = max(max_model_size, 70)
            elif any(x in model_name for x in ['30b', '34b', '40b']):
                max_model_size = max(max_model_size, 34)
            elif any(x in model_name for x in ['13b', '14b', '15b', '20b']):
                max_model_size = max(max_model_size, 14)
            elif any(x in model_name for x in ['7b', '8b']):
                max_model_size = max(max_model_size, 8)
            elif any(x in model_name for x in ['3b', '4b']):
                max_model_size = max(max_model_size, 4)
        
        # Оцениваем VRAM на основе максимальной модели
        # Правило: модель требует ~1.2 GB VRAM на 1B параметров (Q4 квантизация)
        if max_model_size >= 70:
            # 70B модель требует ~40-48 GB VRAM -> 2-3x RTX 3090
            resource_info = {
                "gpu_count": 2,
                "gpu_memory_gb": 24,
                "total_gpu_memory_gb": 48
            }
        elif max_model_size >= 34:
            # 34B модель требует ~24 GB -> 1x RTX 3090
            resource_info = {
                "gpu_count": 1,
                "gpu_memory_gb": 24,
                "total_gpu_memory_gb": 24
            }
        elif max_model_size >= 14:
            # 14B модель требует ~10-12 GB -> RTX 3080/4080
            resource_info = {
                "gpu_count": 1,
                "gpu_memory_gb": 16,
                "total_gpu_memory_gb": 16
            }
        elif max_model_size >= 8:
            # 7B-8B модель требует ~6-8 GB -> RTX 3060/3070
            resource_info = {
                "gpu_count": 1,
                "gpu_memory_gb": 8,
                "total_gpu_memory_gb": 8
            }
        else:
            # Маленькие модели -> предполагаем минимум
            resource_info = {
                "gpu_count": 1,
                "gpu_memory_gb": 6,
                "total_gpu_memory_gb": 6
            }
        
        return resource_info
    
    def _get_local_gpu_info(self) -> Dict[str, Any]:
        """Получает информацию о локальных GPU через nvidia-smi"""
        resource_info = {
            "gpu_count": 0,
            "gpu_memory_gb": 0,
            "total_gpu_memory_gb": 0
        }
        
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total,name", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                resource_info["gpu_count"] = len(lines)
                total_mem = 0
                for line in lines:
                    parts = line.split(',')
                    if parts:
                        total_mem += float(parts[0].strip())
                resource_info["total_gpu_memory_gb"] = total_mem / 1024
                resource_info["gpu_memory_gb"] = total_mem / len(lines) / 1024
                
                logger.debug(f"Local GPU resources: {resource_info['gpu_count']} GPUs, {resource_info['total_gpu_memory_gb']:.1f} GB total")
        except Exception as e:
            logger.debug(f"Failed to get local GPU info: {e}")
        
        return resource_info
    
    def _determine_resource_level(self, total_gpu_memory: float, gpu_count: int) -> str:
        """Определяет уровень ресурсов"""
        if total_gpu_memory >= 48:  # 2+ RTX 3090
            return "maximum"
        elif total_gpu_memory >= 24:  # 1x RTX 3090
            return "high"
        elif total_gpu_memory >= 12:  # RTX 3080 или меньше
            return "medium"
        elif total_gpu_memory >= 6:
            return "low"
        else:
            return "minimal"
    
    def _get_resource_multiplier(self, resource_info: Dict[str, Any]) -> float:
        """
        Вычисляет множитель времени на основе доступных ресурсов
        
        Больше ресурсов = меньше время = меньший множитель
        """
        level = resource_info.get("resource_level", "medium")
        gpu_count = resource_info.get("gpu_count", 1)
        
        # Базовые множители по уровню ресурсов
        level_multipliers = {
            "maximum": 0.5,   # 2+ мощных GPU — в 2 раза быстрее
            "high": 0.7,      # 1 мощный GPU
            "medium": 1.0,    # Базовый уровень
            "low": 1.5,       # Слабые ресурсы
            "minimal": 2.5    # Очень слабые ресурсы
        }
        
        base_mult = level_multipliers.get(level, 1.0)
        
        # Дополнительная корректировка на multi-GPU
        if gpu_count >= 3:
            base_mult *= 0.6  # 3+ GPU значительно ускоряют
        elif gpu_count >= 2:
            base_mult *= 0.75  # 2 GPU дают хороший буст
        
        return base_mult

    def analyze(
        self,
        task: str,
        model: Optional[str] = None,
        task_type: Optional[str] = None
    ) -> ComplexityEstimate:
        """
        Анализирует сложность задачи с учётом ДИНАМИЧЕСКИХ ресурсов
        
        Args:
            task: Текст задачи
            model: Используемая модель (для корректировки времени)
            task_type: Тип задачи если известен
            
        Returns:
            ComplexityEstimate с оценкой и предупреждением
        """
        task_lower = task.lower()
        factors = {}
        
        # Получаем информацию о ресурсах (динамически!)
        resource_info = self._get_resource_info_sync()
        factors["resources"] = {
            "gpu_count": resource_info["gpu_count"],
            "total_gpu_memory_gb": resource_info["total_gpu_memory_gb"],
            "resource_level": resource_info["resource_level"]
        }
        
        # 1. Определяем базовую сложность по ключевым словам
        base_level = self._detect_complexity_by_keywords(task_lower)
        factors["keyword_level"] = base_level.value
        
        # 2. Корректируем по паттернам
        pattern_multiplier = self._calculate_pattern_multiplier(task_lower)
        factors["pattern_multiplier"] = pattern_multiplier
        
        # 3. Учитываем длину задачи
        length_factor = self._calculate_length_factor(task)
        factors["length_factor"] = length_factor
        
        # 4. Проверяем наличие множественных требований
        multi_factor = self._check_multiple_requirements(task_lower)
        factors["multi_requirements"] = multi_factor
        
        # 5. Вычисляем финальную сложность
        complexity_score = self._calculate_final_score(
            base_level, pattern_multiplier, length_factor, multi_factor
        )
        
        final_level = self._score_to_level(complexity_score)
        factors["final_score"] = complexity_score
        
        # 6. Оцениваем время с учётом ресурсов
        estimated_minutes = self._estimate_time(final_level, model)
        
        # Корректируем на модель
        if model:
            model_multiplier = self._get_model_time_multiplier(model)
            estimated_minutes *= model_multiplier
            factors["model_multiplier"] = model_multiplier
        
        # Корректируем на ДИНАМИЧЕСКИЕ ресурсы системы
        resource_multiplier = self._get_resource_multiplier(resource_info)
        estimated_minutes *= resource_multiplier
        factors["resource_multiplier"] = resource_multiplier
        
        # Логируем для отладки
        if resource_multiplier != 1.0:
            logger.debug(
                f"Resource adjustment: {resource_info['resource_level']} level, "
                f"{resource_info['gpu_count']} GPUs -> {resource_multiplier:.2f}x multiplier"
            )
        
        # 7. Генерируем предупреждение (если нужно) с учётом ресурсов
        warning_message, should_warn = self._generate_warning(
            final_level, estimated_minutes, task, resource_info
        )
        
        return ComplexityEstimate(
            level=final_level,
            estimated_minutes=estimated_minutes,
            warning_message=warning_message,
            should_warn=should_warn,
            factors=factors
        )
    
    def _detect_complexity_by_keywords(self, task_lower: str) -> ComplexityLevel:
        """Определяет сложность по ключевым словам"""
        for level_name, keywords in self.COMPLEX_KEYWORDS.items():
            for keyword in keywords:
                if keyword in task_lower:
                    return ComplexityLevel[level_name.upper()]
        
        return ComplexityLevel.SIMPLE
    
    def _calculate_pattern_multiplier(self, task_lower: str) -> float:
        """Вычисляет множитель на основе паттернов"""
        multiplier = 1.0
        
        for pattern, weight in self.CODE_PATTERNS:
            if re.search(pattern, task_lower, re.IGNORECASE):
                multiplier = max(multiplier, weight)
        
        return multiplier
    
    def _calculate_length_factor(self, task: str) -> float:
        """Фактор на основе длины задачи"""
        length = len(task)
        
        if length < 50:
            return 0.8  # Короткие задачи обычно простые
        elif length < 200:
            return 1.0
        elif length < 500:
            return 1.3
        elif length < 1000:
            return 1.6
        else:
            return 2.0  # Очень длинные задачи обычно сложные
    
    def _check_multiple_requirements(self, task_lower: str) -> float:
        """Проверяет наличие множественных требований"""
        # Ключевые слова множественности
        multi_keywords = [
            "и также", "а также", "плюс", "кроме того",
            "дополнительно", "ещё", "еще", "потом",
            "после этого", "затем", "and also", "plus",
            "additionally", "then", "after that"
        ]
        
        count = sum(1 for kw in multi_keywords if kw in task_lower)
        
        # Считаем пункты списка
        list_items = len(re.findall(r'^\s*[-•\d]+[.)]?\s+', task_lower, re.MULTILINE))
        count += list_items
        
        if count >= 5:
            return 2.0
        elif count >= 3:
            return 1.5
        elif count >= 1:
            return 1.2
        return 1.0
    
    def _calculate_final_score(
        self,
        base_level: ComplexityLevel,
        pattern_mult: float,
        length_factor: float,
        multi_factor: float
    ) -> float:
        """Вычисляет финальный скор сложности"""
        level_scores = {
            ComplexityLevel.TRIVIAL: 1.0,
            ComplexityLevel.SIMPLE: 2.0,
            ComplexityLevel.MODERATE: 3.0,
            ComplexityLevel.COMPLEX: 4.0,
            ComplexityLevel.VERY_COMPLEX: 5.0,
            ComplexityLevel.EXTREME: 6.0,
        }
        
        base_score = level_scores[base_level]
        final_score = base_score * pattern_mult * length_factor * multi_factor
        
        return min(final_score, 10.0)  # Максимум 10
    
    def _score_to_level(self, score: float) -> ComplexityLevel:
        """Преобразует скор в уровень сложности"""
        if score < 1.5:
            return ComplexityLevel.TRIVIAL
        elif score < 2.5:
            return ComplexityLevel.SIMPLE
        elif score < 4.0:
            return ComplexityLevel.MODERATE
        elif score < 6.0:
            return ComplexityLevel.COMPLEX
        elif score < 8.0:
            return ComplexityLevel.VERY_COMPLEX
        else:
            return ComplexityLevel.EXTREME
    
    def _estimate_time(self, level: ComplexityLevel, model: Optional[str]) -> float:
        """Оценивает время выполнения в минутах"""
        return self.default_time_estimates.get(level, 5.0)
    
    def _get_model_time_multiplier(self, model: str) -> float:
        """Множитель времени для модели"""
        model_lower = model.lower()
        
        # Маленькие модели медленнее на сложных задачах
        if any(x in model_lower for x in ["1b", "2b", "3b"]):
            return 2.0  # В 2 раза дольше
        elif any(x in model_lower for x in ["7b", "8b"]):
            return 1.3
        elif any(x in model_lower for x in ["13b", "14b"]):
            return 1.0  # Базовое время
        elif any(x in model_lower for x in ["30b", "34b"]):
            return 0.9
        elif any(x in model_lower for x in ["70b", "72b"]):
            return 0.8  # Большие модели быстрее справляются
        
        return 1.0
    
    def _generate_warning(
        self,
        level: ComplexityLevel,
        estimated_minutes: float,
        task: str,
        resource_info: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[str], bool]:
        """
        Генерирует предупреждение для пользователя с учётом ресурсов
        
        Returns:
            (warning_message, should_warn)
        """
        # Не предупреждаем для простых задач
        if level in [ComplexityLevel.TRIVIAL, ComplexityLevel.SIMPLE]:
            return None, False
        
        # Формируем информацию о ресурсах для отображения
        resource_note = ""
        if resource_info:
            gpu_count = resource_info.get("gpu_count", 0)
            total_vram = resource_info.get("total_gpu_memory_gb", 0)
            res_level = resource_info.get("resource_level", "medium")
            
            if gpu_count >= 2:
                resource_note = f"\n🎮 Используется: {gpu_count} GPU ({total_vram:.0f} GB VRAM)"
            elif gpu_count == 1 and total_vram >= 20:
                resource_note = f"\n🎮 Используется: GPU {total_vram:.0f} GB VRAM"
            elif res_level in ["low", "minimal"]:
                resource_note = "\n⚡ Совет: более мощные ресурсы ускорят обработку"
        
        # Для умеренных задач - мягкое уведомление
        if level == ComplexityLevel.MODERATE:
            return (
                f"⏱️ Это может занять ~{estimated_minutes:.0f} мин. "
                f"Выполнение началось...{resource_note}",
                True
            )
        
        # Для сложных задач - заметное предупреждение
        if level == ComplexityLevel.COMPLEX:
            return (
                f"⚠️ Сложная задача. Ожидаемое время: ~{estimated_minutes:.0f} мин. "
                f"Пожалуйста, подождите — выполнение уже идёт...{resource_note}",
                True
            )
        
        # Для очень сложных - подробное предупреждение
        if level == ComplexityLevel.VERY_COMPLEX:
            return (
                f"⚠️ Очень сложная задача!\n"
                f"Ожидаемое время: ~{estimated_minutes:.0f} мин (до {int(estimated_minutes * 1.5)} мин).{resource_note}\n"
                f"Система обрабатывает запрос — НЕ прерывайте процесс.\n"
                f"Вы получите результат, когда обработка завершится.",
                True
            )
        
        # Для экстремально сложных - важное предупреждение
        return (
            f"🚨 ОЧЕНЬ сложная задача!\n"
            f"Ожидаемое время: ~{estimated_minutes:.0f} мин (может занять до 60 мин).{resource_note}\n\n"
            f"Это нормально для таких задач как:\n"
            f"• Создание полных приложений\n"
            f"• Генерация больших объёмов кода\n"
            f"• Комплексный анализ\n\n"
            f"Система работает — пожалуйста, дождитесь результата.\n"
            f"Выполнение НЕ заблокировано и уже идёт!",
            True
        )


# Глобальный экземпляр
_complexity_analyzer: Optional[ComplexityAnalyzer] = None


def get_complexity_analyzer() -> ComplexityAnalyzer:
    """Получает глобальный экземпляр анализатора"""
    global _complexity_analyzer
    if _complexity_analyzer is None:
        _complexity_analyzer = ComplexityAnalyzer()
    return _complexity_analyzer


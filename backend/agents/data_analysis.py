"""
DataAnalysisAgent - Analyzes data and creates ML models

Автоматически определяет ML задачи в тексте и запускает обучение.
"""

import re
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
from pathlib import Path
from ..core.logger import get_logger
logger = get_logger(__name__)

from .base import BaseAgent
from ..llm.base import LLMMessage
from ..core.exceptions import AgentException


# Паттерны для автоопределения ML задач
ML_TASK_PATTERNS = {
    "classification": [
        r"классифик\w*", r"classify", r"classification",
        r"predict.*class", r"категор\w*", r"categoriz\w*",
        r"detect\w*", r"распознав\w*", r"определ\w*.*тип"
    ],
    "regression": [
        r"регресс\w*", r"regression", r"predict.*value",
        r"predict.*price", r"прогноз\w*", r"forecast\w*",
        r"предсказ\w*.*цен", r"предсказ\w*.*значен"
    ],
    "clustering": [
        r"кластер\w*", r"cluster\w*", r"segment\w*",
        r"группир\w*", r"group\w*.*similar"
    ],
    "time_series": [
        r"time.?series", r"временн\w*.*ряд\w*",
        r"прогноз\w*.*времен", r"forecast.*time"
    ]
}

# Паттерны для определения файлов данных
DATA_FILE_PATTERNS = [
    r"['\"]([^'\"]+\.csv)['\"]",
    r"['\"]([^'\"]+\.xlsx)['\"]",
    r"['\"]([^'\"]+\.parquet)['\"]",
    r"файл[а-я]*\s+([^\s]+\.(?:csv|xlsx|parquet))",
    r"data[^\s]*\.(?:csv|xlsx|parquet)",
]


class DataAnalysisAgent(BaseAgent):
    """
    Agent for data analysis and machine learning.
    
    Автоматически:
    - Определяет тип ML задачи из текста
    - Находит пути к файлам данных
    - Запускает AutoML обучение
    - Генерирует отчеты с рекомендациями
    """
    
    def _detect_ml_task_type(self, text: str) -> Tuple[Optional[str], float]:
        """
        Определяет тип ML задачи из текста.
        
        Returns:
            (task_type, confidence) - тип задачи и уверенность
        """
        text_lower = text.lower()
        
        scores = {}
        for task_type, patterns in ML_TASK_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, text_lower))
                score += matches
            if score > 0:
                scores[task_type] = score
        
        if not scores:
            return None, 0.0
        
        best_type = max(scores, key=scores.get)
        # Нормализуем confidence (макс 1.0 при 3+ совпадениях)
        confidence = min(scores[best_type] / 3.0, 1.0)
        
        return best_type, confidence
    
    def _extract_data_path(self, text: str, context: Dict[str, Any]) -> Optional[str]:
        """Извлекает путь к файлу данных из текста или контекста."""
        # Сначала проверяем контекст
        if "data_path" in context:
            return context["data_path"]
        
        # Ищем в тексте
        for pattern in DATA_FILE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                path = match.group(1) if match.groups() else match.group(0)
                # Проверяем существование файла
                if Path(path).exists():
                    return path
        
        return None
    
    def _extract_target_column(self, text: str, context: Dict[str, Any]) -> Optional[str]:
        """Извлекает целевую колонку из текста или контекста."""
        if "target_column" in context:
            return context["target_column"]
        
        # Паттерны для определения target
        target_patterns = [
            r"target[:\s]+['\"]?(\w+)['\"]?",
            r"predict[:\s]+['\"]?(\w+)['\"]?",
            r"целев\w*[:\s]+['\"]?(\w+)['\"]?",
            r"предсказ\w*[:\s]+['\"]?(\w+)['\"]?",
            r"колонк[аи]\s+['\"]?(\w+)['\"]?",
        ]
        
        for pattern in target_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    async def _execute_impl(self, task: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute data analysis task with automatic ML task detection.
        
        Args:
            task: Analysis task description
            context: Additional context (data path, columns, etc.)
            
        Returns:
            Analysis results with optional AutoML training
        """
        logger.info(f"DataAnalysisAgent executing task: {task}")
        
        # Автоопределение типа ML задачи
        detected_task_type, confidence = self._detect_ml_task_type(task)
        if detected_task_type and confidence >= 0.5:
            logger.info(f"Detected ML task type: {detected_task_type} (confidence: {confidence:.2f})")
            if "task_type" not in context:
                context["task_type"] = detected_task_type
        
        # Автоопределение пути к данным
        data_path = self._extract_data_path(task, context)
        if data_path:
            context["data_path"] = data_path
            logger.info(f"Detected data path: {data_path}")
        
        # Автоопределение целевой колонки
        target_column = self._extract_target_column(task, context)
        if target_column:
            context["target_column"] = target_column
            logger.info(f"Detected target column: {target_column}")
        
        # Get context
        context_text = await self._get_context(task)
        
        # Определяем, нужно ли автоматически запускать AutoML
        auto_train = (
            detected_task_type in ["classification", "regression"] and
            confidence >= 0.6 and
            "data_path" in context and
            "target_column" in context
        )
        
        system_prompt = """You are an expert data scientist and machine learning engineer. Your task is to analyze data, create models, and provide insights.

Capabilities:
- Exploratory Data Analysis (EDA)
- Statistical analysis
- Feature engineering
- Model selection and training
- Model evaluation
- Visualization recommendations
- Time series analysis
- Clustering and classification

Provide detailed analysis with code examples and recommendations."""
        
        user_prompt = f"""Data Analysis Task: {task}

"""
        
        if context_text:
            user_prompt += f"Relevant context:\n{context_text}\n\n"
        
        if context:
            if "data_path" in context:
                user_prompt += f"Data file path: {context['data_path']}\n"
            if "columns" in context:
                user_prompt += f"Columns: {', '.join(context['columns'])}\n"
            if "target_column" in context:
                user_prompt += f"Target column: {context['target_column']}\n"
            if "task_type" in context:
                user_prompt += f"Task type: {context['task_type']} (classification/regression/clustering)\n"
        
        # Информируем о доступности AutoML
        if auto_train:
            user_prompt += "\n\n🤖 AutoML training will be automatically executed for this task."
        elif self.automl_engine and "data_path" in context:
            user_prompt += "\n\nNote: AutoML training is available. Specify target_column to enable."
        
        user_prompt += "\nPlease provide a comprehensive analysis with code and recommendations."
        
        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt)
        ]
        
        try:
            analysis = await self._get_llm_response(messages)
            
            result = {
                "agent": self.name,
                "task": task,
                "analysis": analysis,
                "success": True,
                "detected_task_type": detected_task_type,
                "detection_confidence": confidence
            }
            
            # Автоматический или явный запуск AutoML
            should_train = auto_train or ("data_path" in context and "target_column" in context)
            
            if should_train:
                automl_engine = await self._get_automl_engine()
                if automl_engine:
                    try:
                        logger.info(f"Starting AutoML training: {context.get('task_type', 'auto')}")
                        automl_result = await automl_engine.auto_train(
                            data_path=context["data_path"],
                            target_column=context["target_column"],
                            task_type=context.get("task_type", "auto")
                        )
                        result["automl_result"] = automl_result
                        result["automl_auto_triggered"] = auto_train
                        
                        # Добавляем саммари результатов
                        if automl_result.get("success") and automl_result.get("best_model"):
                            best = automl_result["best_model"]
                            result["summary"] = (
                                f"✅ AutoML completed! Best model: {best.get('name', 'Unknown')} "
                                f"with score {best.get('score', 0):.4f}"
                            )
                    except Exception as e:
                        logger.warning(f"AutoML training failed: {e}")
                        result["automl_error"] = str(e)
            
            # Save to memory
            if self.memory:
                await self.memory.save_solution(
                    task=task,
                    solution=analysis,
                    agent=self.name,
                    metadata={
                        **context,
                        "detected_task_type": detected_task_type,
                        "automl_triggered": should_train
                    }
                )
            
            return result
            
        except Exception as e:
            logger.error(f"DataAnalysisAgent error: {e}")
            raise AgentException(f"Data analysis failed: {e}") from e
    
    async def perform_eda(self, data_path: str) -> Dict[str, Any]:
        """
        Perform Exploratory Data Analysis
        
        Args:
            data_path: Path to data file
            
        Returns:
            EDA results
        """
        try:
            # Load data
            if data_path.endswith('.csv'):
                df = pd.read_csv(data_path)
            elif data_path.endswith('.xlsx'):
                df = pd.read_excel(data_path)
            else:
                raise ValueError(f"Unsupported file format: {data_path}")
            
            # Basic statistics
            stats = {
                "shape": df.shape,
                "columns": df.columns.tolist(),
                "dtypes": df.dtypes.to_dict(),
                "missing_values": df.isnull().sum().to_dict(),
                "numeric_summary": df.describe().to_dict() if len(df.select_dtypes(include=[np.number]).columns) > 0 else {},
                "categorical_summary": {}
            }
            
            # Categorical columns
            cat_cols = df.select_dtypes(include=['object']).columns
            for col in cat_cols:
                stats["categorical_summary"][col] = df[col].value_counts().to_dict()
            
            return {
                "success": True,
                "statistics": stats,
                "recommendations": self._generate_eda_recommendations(stats)
            }
        except Exception as e:
            logger.error(f"EDA error: {e}")
            return {"success": False, "error": str(e)}
    
    def _generate_eda_recommendations(self, stats: Dict[str, Any]) -> list:
        """Generate recommendations based on EDA"""
        recommendations = []
        
        # Check for missing values
        missing = stats.get("missing_values", {})
        if any(v > 0 for v in missing.values()):
            recommendations.append("Consider handling missing values (imputation or removal)")
        
        # Check data types
        if stats.get("shape", [0, 0])[0] < 100:
            recommendations.append("Small dataset - consider data augmentation or collecting more data")
        
        return recommendations


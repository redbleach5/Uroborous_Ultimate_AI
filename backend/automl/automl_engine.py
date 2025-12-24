"""
AutoML Engine - Automatic model selection and training
"""

from typing import Dict, Any, Optional, List
import pandas as pd
import numpy as np
from ..core.logger import get_logger
logger = get_logger(__name__)

try:
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, r2_score, mean_squared_error
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LogisticRegression, LinearRegression
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available")

from .model_trainer import ModelTrainer
from .hyperparameter_optimizer import HyperparameterOptimizer


class AutoMLEngine:
    """AutoML engine for automatic model selection and training"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize AutoML engine
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.frameworks = self.config.get("frameworks", ["sklearn", "xgboost", "lightgbm"])
        self.optimization_enabled = self.config.get("optimization", {}).get("enabled", True)
        
        self.model_trainer = ModelTrainer(config)
        self.hyperparameter_optimizer = HyperparameterOptimizer(config) if self.optimization_enabled else None
    
    async def auto_train(
        self,
        data_path: str,
        target_column: str,
        task_type: str = "auto",  # classification, regression, clustering
        test_size: float = 0.2
    ) -> Dict[str, Any]:
        """
        Automatically train models on data
        
        Args:
            data_path: Path to data file
            target_column: Name of target column
            task_type: Type of task (auto-detect if "auto")
            test_size: Test set size
            
        Returns:
            Training results with best model
        """
        if not SKLEARN_AVAILABLE:
            return {"success": False, "error": "scikit-learn not available"}
        
        try:
            # Load data
            df = pd.read_csv(data_path)
            
            # Prepare features and target
            X = df.drop(columns=[target_column])
            y = df[target_column]
            
            # Auto-detect task type
            if task_type == "auto":
                if y.dtype == "object" or y.nunique() < 20:
                    task_type = "classification"
                else:
                    task_type = "regression"
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42
            )
            
            # Try different models
            models_to_try = self._get_models_for_task(task_type)
            
            results = []
            best_model = None
            best_score = -np.inf if task_type == "regression" else 0
            
            for model_name, model_class in models_to_try:
                try:
                    logger.info(f"Training {model_name}...")
                    
                    # Train model
                    model = model_class()
                    model.fit(X_train, y_train)
                    
                    # Evaluate
                    y_pred = model.predict(X_test)
                    
                    if task_type == "classification":
                        score = accuracy_score(y_test, y_pred)
                        metrics = {
                            "accuracy": score,
                            "precision": precision_score(y_test, y_pred, average="weighted", zero_division=0),
                            "recall": recall_score(y_test, y_pred, average="weighted", zero_division=0),
                            "f1": f1_score(y_test, y_pred, average="weighted", zero_division=0)
                        }
                    else:  # regression
                        score = r2_score(y_test, y_pred)
                        metrics = {
                            "r2": score,
                            "mse": mean_squared_error(y_test, y_pred),
                            "rmse": np.sqrt(mean_squared_error(y_test, y_pred))
                        }
                    
                    results.append({
                        "model": model_name,
                        "score": score,
                        "metrics": metrics
                    })
                    
                    # Update best model
                    if (task_type == "classification" and score > best_score) or \
                       (task_type == "regression" and score > best_score):
                        best_score = score
                        best_model = {
                            "name": model_name,
                            "model": model,
                            "score": score,
                            "metrics": metrics
                        }
                    
                except Exception as e:
                    logger.warning(f"Failed to train {model_name}: {e}")
                    continue
            
            return {
                "success": True,
                "task_type": task_type,
                "best_model": best_model,
                "all_results": results,
                "training_samples": len(X_train),
                "test_samples": len(X_test)
            }
            
        except Exception as e:
            logger.error(f"AutoML training error: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_models_for_task(self, task_type: str) -> List[tuple]:
        """Get models to try for task type"""
        models = []
        
        if task_type == "classification":
            if "sklearn" in self.frameworks:
                models.append(("LogisticRegression", LogisticRegression))
                models.append(("RandomForestClassifier", RandomForestClassifier))
            if "xgboost" in self.frameworks:
                models.append(("XGBoostClassifier", xgb.XGBClassifier))
            if "lightgbm" in self.frameworks:
                models.append(("LightGBMClassifier", lgb.LGBMClassifier))
        elif task_type == "regression":
            if "sklearn" in self.frameworks:
                models.append(("LinearRegression", LinearRegression))
                models.append(("RandomForestRegressor", RandomForestRegressor))
            if "xgboost" in self.frameworks:
                models.append(("XGBoostRegressor", xgb.XGBRegressor))
            if "lightgbm" in self.frameworks:
                models.append(("LightGBMRegressor", lgb.LGBMRegressor))
        
        return models
    
    async def optimize_hyperparameters(
        self,
        model_class,
        X_train,
        y_train,
        task_type: str
    ) -> Dict[str, Any]:
        """
        Optimize hyperparameters for a model
        
        Args:
            model_class: Model class to optimize
            X_train: Training features
            y_train: Training target
            task_type: Task type
            
        Returns:
            Optimization results
        """
        if not self.hyperparameter_optimizer:
            return {"success": False, "error": "Hyperparameter optimization not enabled"}
        
        return await self.hyperparameter_optimizer.optimize(
            model_class, X_train, y_train, task_type
        )


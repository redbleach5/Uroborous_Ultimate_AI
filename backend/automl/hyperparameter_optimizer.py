"""
Hyperparameter Optimizer - Optimizes model hyperparameters
"""

from typing import Dict, Any, Optional
from ..core.logger import get_logger
logger = get_logger(__name__)

try:
    import optuna
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    logger.warning("Optuna not available, hyperparameter optimization disabled")


class HyperparameterOptimizer:
    """Optimizes hyperparameters using Optuna"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize hyperparameter optimizer
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
        self.framework = self.config.get("optimization", {}).get("framework", "optuna")
        self.n_trials = self.config.get("optimization", {}).get("n_trials", 100)
        self.timeout = self.config.get("optimization", {}).get("timeout", 3600)
    
    async def optimize(
        self,
        model_class,
        X_train,
        y_train,
        task_type: str
    ) -> Dict[str, Any]:
        """
        Optimize hyperparameters
        
        Args:
            model_class: Model class to optimize
            X_train: Training features
            y_train: Training target
            task_type: Task type
            
        Returns:
            Optimization results
        """
        if not OPTUNA_AVAILABLE:
            return {"success": False, "error": "Optuna not available"}
        
        try:
            # Create study
            study = optuna.create_study(
                direction="maximize" if task_type == "classification" else "maximize"
            )
            
            # Define objective function
            def objective(trial):
                # Suggest hyperparameters based on model type
                if "XGBoost" in model_class.__name__:
                    params = {
                        "n_estimators": trial.suggest_int("n_estimators", 50, 300),
                        "max_depth": trial.suggest_int("max_depth", 3, 10),
                        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3),
                        "subsample": trial.suggest_float("subsample", 0.6, 1.0)
                    }
                elif "LightGBM" in model_class.__name__:
                    params = {
                        "n_estimators": trial.suggest_int("n_estimators", 50, 300),
                        "max_depth": trial.suggest_int("max_depth", 3, 10),
                        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3),
                        "num_leaves": trial.suggest_int("num_leaves", 20, 300)
                    }
                elif "RandomForest" in model_class.__name__:
                    params = {
                        "n_estimators": trial.suggest_int("n_estimators", 50, 300),
                        "max_depth": trial.suggest_int("max_depth", 3, 20),
                        "min_samples_split": trial.suggest_int("min_samples_split", 2, 20)
                    }
                else:
                    # Default parameters
                    params = {}
                
                # Create and train model
                model = model_class(**params)
                model.fit(X_train, y_train)
                
                # Evaluate
                score = model.score(X_train, y_train)
                return score
            
            # Optimize
            study.optimize(objective, n_trials=self.n_trials, timeout=self.timeout)
            
            return {
                "success": True,
                "best_params": study.best_params,
                "best_score": study.best_value,
                "n_trials": len(study.trials)
            }
            
        except Exception as e:
            logger.error(f"Hyperparameter optimization error: {e}")
            return {"success": False, "error": str(e)}


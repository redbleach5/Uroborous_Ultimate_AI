"""
Model Trainer - Trains ML models
"""

from typing import Dict, Any, Optional
import pandas as pd
from ..core.logger import get_logger
logger = get_logger(__name__)

try:
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import accuracy_score, r2_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


class ModelTrainer:
    """Trains machine learning models"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize model trainer
        
        Args:
            config: Configuration dictionary
        """
        self.config = config or {}
    
    async def train_model(
        self,
        model,
        X: pd.DataFrame,
        y: pd.Series,
        test_size: float = 0.2,
        cross_validate: bool = True
    ) -> Dict[str, Any]:
        """
        Train a model
        
        Args:
            model: Model instance to train
            X: Features
            y: Target
            test_size: Test set size
            cross_validate: Whether to perform cross-validation
            
        Returns:
            Training results
        """
        if not SKLEARN_AVAILABLE:
            return {"success": False, "error": "scikit-learn not available"}
        
        try:
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=42
            )
            
            # Train model
            model.fit(X_train, y_train)
            
            # Evaluate
            train_score = model.score(X_train, y_train)
            test_score = model.score(X_test, y_test)
            
            results = {
                "success": True,
                "train_score": float(train_score),
                "test_score": float(test_score),
                "training_samples": len(X_train),
                "test_samples": len(X_test)
            }
            
            # Cross-validation
            if cross_validate:
                cv_scores = cross_val_score(model, X_train, y_train, cv=5)
                results["cv_mean"] = float(cv_scores.mean())
                results["cv_std"] = float(cv_scores.std())
            
            return results
            
        except Exception as e:
            logger.error(f"Model training error: {e}")
            return {"success": False, "error": str(e)}
    
    async def evaluate_model(
        self,
        model,
        X_test: pd.DataFrame,
        y_test: pd.Series,
        task_type: str = "classification"
    ) -> Dict[str, Any]:
        """
        Evaluate a trained model
        
        Args:
            model: Trained model
            X_test: Test features
            y_test: Test target
            task_type: Task type (classification/regression)
            
        Returns:
            Evaluation metrics
        """
        if not SKLEARN_AVAILABLE:
            return {"success": False, "error": "scikit-learn not available"}
        
        try:
            y_pred = model.predict(X_test)
            
            if task_type == "classification":
                score = accuracy_score(y_test, y_pred)
                metrics = {"accuracy": float(score)}
            else:  # regression
                score = r2_score(y_test, y_pred)
                metrics = {"r2": float(score)}
            
            return {
                "success": True,
                "score": float(score),
                "metrics": metrics
            }
            
        except Exception as e:
            logger.error(f"Model evaluation error: {e}")
            return {"success": False, "error": str(e)}


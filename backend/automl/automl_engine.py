"""
AutoML Engine - Automatic model selection and training
"""

from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
import numpy as np
from ..core.logger import get_logger
logger = get_logger(__name__)

SKLEARN_AVAILABLE = False
XGB_AVAILABLE = False
LGB_AVAILABLE = False

try:
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, r2_score, mean_squared_error
    from sklearn.preprocessing import LabelEncoder, OneHotEncoder
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.linear_model import LogisticRegression, LinearRegression
    SKLEARN_AVAILABLE = True
except (ImportError, OSError, TypeError) as e:
    logger.warning(f"scikit-learn not available: {e}")

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except (ImportError, OSError, TypeError) as e:
    xgb = None
    logger.warning(f"xgboost not available: {e}")

try:
    import lightgbm as lgb
    LGB_AVAILABLE = True
except (ImportError, OSError, TypeError) as e:
    lgb = None
    logger.warning(f"lightgbm not available: {e}")

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
        
        # Preprocessing settings
        self.max_categorical_cardinality = self.config.get("max_categorical_cardinality", 50)
        self.handle_missing = self.config.get("handle_missing", True)
    
    def _preprocess_data(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        task_type: str,
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """
        Preprocess data: handle categorical variables, missing values, and encode target.
        
        Args:
            X: Feature DataFrame
            y: Target Series
            task_type: 'classification' or 'regression'
            
        Returns:
            Tuple of (X_processed, y_processed, preprocessing_info)
        """
        preprocessing_info = {
            "categorical_columns": [],
            "numeric_columns": [],
            "dropped_columns": [],
            "target_encoder": None,
        }
        
        # Identify column types
        categorical_cols = []
        numeric_cols = []
        dropped_cols = []
        
        for col in X.columns:
            if X[col].dtype == 'object' or X[col].dtype.name == 'category':
                # Check cardinality
                cardinality = X[col].nunique()
                if cardinality <= self.max_categorical_cardinality:
                    categorical_cols.append(col)
                else:
                    dropped_cols.append(col)
                    logger.warning(
                        f"Dropping column '{col}' - cardinality {cardinality} > {self.max_categorical_cardinality}"
                    )
            elif np.issubdtype(X[col].dtype, np.number):
                numeric_cols.append(col)
            else:
                dropped_cols.append(col)
                logger.warning(f"Dropping column '{col}' - unsupported dtype {X[col].dtype}")
        
        preprocessing_info["categorical_columns"] = categorical_cols
        preprocessing_info["numeric_columns"] = numeric_cols
        preprocessing_info["dropped_columns"] = dropped_cols
        
        # Drop high-cardinality/unsupported columns
        X = X.drop(columns=dropped_cols, errors='ignore')
        
        # Build preprocessor
        transformers = []
        
        if numeric_cols:
            numeric_transformer = Pipeline(steps=[
                ('imputer', SimpleImputer(strategy='median')),
            ])
            transformers.append(('num', numeric_transformer, numeric_cols))
        
        if categorical_cols:
            categorical_transformer = Pipeline(steps=[
                ('imputer', SimpleImputer(strategy='constant', fill_value='_missing_')),
                ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
            ])
            transformers.append(('cat', categorical_transformer, categorical_cols))
        
        if transformers:
            preprocessor = ColumnTransformer(transformers=transformers, remainder='drop')
            X_processed = preprocessor.fit_transform(X)
            preprocessing_info["preprocessor"] = preprocessor
        else:
            X_processed = X.values
        
        # Encode target for classification
        y_processed = y.copy()
        if task_type == "classification" and y.dtype == 'object':
            label_encoder = LabelEncoder()
            y_processed = label_encoder.fit_transform(y)
            preprocessing_info["target_encoder"] = label_encoder
            preprocessing_info["target_classes"] = list(label_encoder.classes_)
        else:
            y_processed = y.values
        
        logger.info(
            f"Preprocessing: {len(numeric_cols)} numeric, {len(categorical_cols)} categorical, "
            f"{len(dropped_cols)} dropped columns"
        )
        
        return X_processed, y_processed, preprocessing_info
    
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
            
            # Validate target column
            if target_column not in df.columns:
                return {"success": False, "error": f"Target column '{target_column}' not found in data"}
            
            # Prepare features and target
            X = df.drop(columns=[target_column])
            y = df[target_column]
            
            # Auto-detect task type
            if task_type == "auto":
                if y.dtype == "object" or y.nunique() < 20:
                    task_type = "classification"
                else:
                    task_type = "regression"
            
            # Preprocess data (handle categorical variables, missing values, etc.)
            X_processed, y_processed, preprocessing_info = self._preprocess_data(X, y, task_type)
            
            if X_processed.shape[1] == 0:
                return {"success": False, "error": "No valid features after preprocessing"}
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X_processed, y_processed, test_size=test_size, random_state=42
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
                "test_samples": len(X_test),
                "preprocessing": {
                    "categorical_columns": preprocessing_info.get("categorical_columns", []),
                    "numeric_columns": preprocessing_info.get("numeric_columns", []),
                    "dropped_columns": preprocessing_info.get("dropped_columns", []),
                    "target_classes": preprocessing_info.get("target_classes"),
                    "feature_count": X_processed.shape[1],
                },
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


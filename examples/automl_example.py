"""
Example: AutoML usage
"""

import asyncio
import pandas as pd
from backend.automl import AutoMLEngine


async def main():
    """Example AutoML usage"""
    
    # Initialize AutoML engine
    automl = AutoMLEngine({
        "enabled": True,
        "frameworks": ["sklearn", "xgboost", "lightgbm"],
        "optimization": {
            "enabled": True,
            "framework": "optuna",
            "n_trials": 50
        }
    })
    
    # Example: Auto-train on data
    # Replace with actual data path
    # result = await automl.auto_train(
    #     data_path="data/train.csv",
    #     target_column="target",
    #     task_type="auto",  # or "classification" or "regression"
    #     test_size=0.2
    # )
    
    # print(f"Best model: {result.get('best_model', {}).get('name')}")
    # print(f"Best score: {result.get('best_model', {}).get('score')}")
    # print(f"All results: {result.get('all_results', [])}")
    
    # Example: Create sample data for demonstration
    print("Creating sample data...")
    from sklearn.datasets import make_classification
    
    X, y = make_classification(
        n_samples=1000,
        n_features=20,
        n_informative=10,
        n_redundant=10,
        n_classes=2,
        random_state=42
    )
    
    df = pd.DataFrame(X, columns=[f"feature_{i}" for i in range(20)])
    df["target"] = y
    
    # Save sample data
    df.to_csv("sample_data.csv", index=False)
    print("Sample data saved to sample_data.csv")
    
    # Train models
    print("\nTraining models...")
    result = await automl.auto_train(
        data_path="sample_data.csv",
        target_column="target",
        task_type="classification",
        test_size=0.2
    )
    
    if result.get("success"):
        print(f"\n✓ Training completed!")
        print(f"Best model: {result['best_model']['name']}")
        print(f"Best accuracy: {result['best_model']['score']:.4f}")
        print(f"\nAll models tested:")
        for model_result in result['all_results']:
            print(f"  - {model_result['model']}: {model_result['score']:.4f}")
    else:
        print(f"Error: {result.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())


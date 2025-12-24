"""
Example: Using different agents
"""

import asyncio
from backend.core.engine import IDAEngine
from backend.config import get_config


async def main():
    """Example usage of different agents"""
    
    config = get_config()
    engine = IDAEngine(config)
    await engine.initialize()
    
    try:
        # 1. CodeWriterAgent - Generate code
        print("=== CodeWriterAgent ===")
        result = await engine.execute_task(
            task="Create a Python function that calculates the factorial of a number",
            agent_type="code_writer"
        )
        print(f"Generated code:\n{result.get('code', 'N/A')}\n")
        
        # 2. ResearchAgent - Research codebase
        print("=== ResearchAgent ===")
        result = await engine.execute_task(
            task="Analyze the project structure and identify main components",
            agent_type="research"
        )
        print(f"Research report:\n{result.get('report', 'N/A')[:500]}...\n")
        
        # 3. DataAnalysisAgent - Analyze data
        print("=== DataAnalysisAgent ===")
        result = await engine.execute_task(
            task="Perform exploratory data analysis on a dataset with features and target column",
            agent_type="data_analysis",
            context={
                "task_type": "classification",
                "columns": ["feature1", "feature2", "target"]
            }
        )
        print(f"Analysis:\n{result.get('analysis', 'N/A')[:500]}...\n")
        
        # 4. ReactAgent - Interactive problem solving
        print("=== ReactAgent ===")
        result = await engine.execute_task(
            task="Read the README.md file and summarize its contents",
            agent_type="react"
        )
        print(f"Final answer:\n{result.get('final_answer', 'N/A')}\n")
        
        # 5. WorkflowAgent - Manage workflows
        print("=== WorkflowAgent ===")
        result = await engine.execute_task(
            task="Create a workflow for data preprocessing, model training, and evaluation",
            agent_type="workflow"
        )
        print(f"Workflow result:\n{result.get('workflow_result', 'N/A')[:500]}...\n")
        
        # 6. IntegrationAgent - API integration
        print("=== IntegrationAgent ===")
        result = await engine.execute_task(
            task="Create code to integrate with a REST API endpoint",
            agent_type="integration",
            context={
                "api_endpoint": "https://api.example.com/data",
                "api_type": "REST"
            }
        )
        print(f"Integration code:\n{result.get('integration_code', 'N/A')[:500]}...\n")
        
        # 7. MonitoringAgent - System monitoring
        print("=== MonitoringAgent ===")
        result = await engine.execute_task(
            task="Monitor system performance and provide recommendations",
            agent_type="monitoring"
        )
        print(f"Monitoring analysis:\n{result.get('analysis', 'N/A')[:500]}...\n")
        print(f"Current metrics: {result.get('current_metrics', {})}\n")
        
    finally:
        await engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())


"""
Basic usage example for AILLM
"""

import asyncio
from backend.core.engine import IDAEngine
from backend.config import get_config


async def main():
    """Example usage"""
    # Load configuration
    config = get_config()
    
    # Initialize engine
    engine = IDAEngine(config)
    await engine.initialize()
    
    try:
        # Example 1: Generate code
        print("Example 1: Generating code...")
        result = await engine.execute_task(
            task="Create a Python function that calculates fibonacci numbers",
            agent_type="code_writer"
        )
        print(f"Result: {result}\n")
        
        # Example 2: Research task
        print("Example 2: Researching codebase...")
        result = await engine.execute_task(
            task="Analyze the project structure and identify main components",
            agent_type="research"
        )
        print(f"Result: {result}\n")
        
        # Example 3: ReAct agent
        print("Example 3: Using ReAct agent...")
        result = await engine.execute_task(
            task="Read the README.md file and summarize its contents",
            agent_type="react"
        )
        print(f"Result: {result}\n")
        
    finally:
        await engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())


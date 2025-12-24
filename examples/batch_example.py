"""
Batch processing example
"""

import asyncio
from backend.core.engine import IDAEngine
from backend.config import get_config


async def main():
    """Batch processing example"""
    
    print("=" * 60)
    print("AILLM Batch Processing Example")
    print("=" * 60)
    
    # Initialize engine
    config = get_config()
    engine = IDAEngine(config)
    await engine.initialize()
    
    try:
        # Example 1: Batch task processing
        print("\n1. Processing batch of tasks...")
        
        tasks = [
            "Create a Python function to calculate factorial",
            "Create a Python function to check if a number is prime",
            "Create a Python function to reverse a string",
            "Create a Python function to find the maximum in a list",
            "Create a Python function to count words in a string"
        ]
        
        results = await engine.batch_processor.process_tasks_batch(
            engine=engine,
            tasks=tasks,
            agent_type="code_writer"
        )
        
        print(f"   ✓ Processed {len(results)} tasks")
        print(f"   ✓ Successful: {sum(1 for r in results if r.get('success'))}")
        print(f"   ✓ Failed: {sum(1 for r in results if not r.get('success'))}")
        
        # Example 2: Batch code generation
        print("\n2. Processing batch of code generation requests...")
        
        code_requests = [
            {
                "task": "Create a TodoList class with add, remove, and list methods",
                "file_path": "todo.py"
            },
            {
                "task": "Create a Calculator class with basic operations",
                "file_path": "calculator.py"
            },
            {
                "task": "Create a User class with authentication methods",
                "file_path": "user.py"
            }
        ]
        
        code_results = await engine.batch_processor.process_code_generation_batch(
            engine=engine,
            code_requests=code_requests
        )
        
        print(f"   ✓ Processed {len(code_results)} code requests")
        print(f"   ✓ Successful: {sum(1 for r in code_results if r.get('success'))}")
        
        # Example 3: Check metrics
        print("\n3. Checking metrics...")
        from backend.core.metrics import metrics_collector
        
        stats = metrics_collector.get_all_stats()
        print(f"   ✓ Total tasks: {stats['tasks']['total']}")
        print(f"   ✓ Success rate: {stats['tasks']['success_rate']:.2%}")
        
        if stats['agents']:
            print(f"   ✓ Agents used: {list(stats['agents'].keys())}")
        
        print("\n" + "=" * 60)
        print("Batch processing example completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())


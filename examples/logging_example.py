"""
Logging example - Demonstrating structured logging
"""

import asyncio
from backend.core.engine import IDAEngine
from backend.config import get_config
from backend.core.logger import structured_logger


async def main():
    """Logging example"""
    
    print("=" * 60)
    print("AILLM Logging Example")
    print("=" * 60)
    
    # Initialize engine
    config = get_config()
    engine = IDAEngine(config)
    await engine.initialize()
    
    try:
        # Example task execution with logging
        print("\n1. Executing task with structured logging...")
        
        task = "Create a Python function to calculate fibonacci numbers"
        
        result = await engine.execute_task(
            task=task,
            agent_type="code_writer"
        )
        
        print(f"   ✓ Task completed: {result.get('success', False)}")
        
        # Log custom event
        print("\n2. Custom logging...")
        structured_logger.log_agent_action(
            agent_name="code_writer",
            action="custom_action",
            task="Custom logging example",
            context={"example": True},
            result={"success": True}
        )
        
        # Get cache stats
        print("\n3. RAG cache statistics...")
        if engine.context_manager and hasattr(engine.context_manager, 'cache'):
            stats = engine.context_manager.cache.get_stats()
            print(f"   Cache size: {stats['size']}/{stats['max_size']}")
            print(f"   TTL: {stats['ttl']}s")
        
        print("\n" + "=" * 60)
        print("Logging example completed!")
        print("=" * 60)
        print("\nCheck logs/app.log and logs/error.log for detailed logs")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())


"""
Metrics example - Demonstrating metrics collection
"""

import asyncio
from backend.core.engine import IDAEngine
from backend.config import get_config
from backend.core.metrics import metrics_collector


async def main():
    """Metrics example"""
    
    print("=" * 60)
    print("AILLM Metrics Example")
    print("=" * 60)
    
    # Initialize engine
    config = get_config()
    engine = IDAEngine(config)
    await engine.initialize()
    
    try:
        # Execute some tasks
        print("\n1. Executing tasks to generate metrics...")
        
        tasks = [
            "Create a simple hello world function",
            "Create a function to add two numbers",
            "Create a function to multiply two numbers"
        ]
        
        for task in tasks:
            await engine.execute_task(
                task=task,
                agent_type="code_writer"
            )
        
        print("   ✓ Tasks executed")
        
        # Get all statistics
        print("\n2. Getting all statistics...")
        stats = metrics_collector.get_all_stats()
        
        print(f"   Tasks:")
        print(f"     Total: {stats['tasks']['total']}")
        print(f"     Success: {stats['tasks']['success']}")
        print(f"     Success rate: {stats['tasks']['success_rate']:.2%}")
        
        if stats['agents']:
            print(f"\n   Agents:")
            for agent_name, agent_stats in stats['agents'].items():
                print(f"     {agent_name}:")
                print(f"       Executions: {agent_stats['total_executions']}")
                print(f"       Success rate: {agent_stats['success_rate']:.2%}")
                print(f"       Avg duration: {agent_stats['avg_duration']:.2f}s")
        
        # Get agent-specific stats
        print("\n3. Getting code_writer agent stats...")
        agent_stats = metrics_collector.get_agent_stats("code_writer")
        print(f"   ✓ Total executions: {agent_stats['total_executions']}")
        print(f"   ✓ Success rate: {agent_stats['success_rate']:.2%}")
        print(f"   ✓ Average duration: {agent_stats['avg_duration']:.2f}s")
        
        # Get recent metrics
        print("\n4. Getting recent metrics (last 60 minutes)...")
        recent = metrics_collector.get_recent_metrics(minutes=60)
        print(f"   ✓ Recent tasks: {len(recent['tasks'])}")
        if recent['agents']:
            print(f"   ✓ Agents with activity: {list(recent['agents'].keys())}")
        
        print("\n" + "=" * 60)
        print("Metrics example completed!")
        print("=" * 60)
        print("\nAccess metrics via API:")
        print("  GET /api/v1/metrics/stats - All statistics")
        print("  GET /api/v1/metrics/agent/{name} - Agent statistics")
        print("  GET /api/v1/metrics/recent?minutes=60 - Recent metrics")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())


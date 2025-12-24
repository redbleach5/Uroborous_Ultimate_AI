"""
Full workflow example - Complete usage of AILLM system
"""

import asyncio
from backend.core.engine import IDAEngine
from backend.config import get_config


async def main():
    """Complete workflow example"""
    
    print("=" * 60)
    print("AILLM Full Workflow Example")
    print("=" * 60)
    
    # Initialize engine
    config = get_config()
    engine = IDAEngine(config)
    await engine.initialize()
    
    try:
        # 1. Index project for RAG
        print("\n1. Indexing project for RAG...")
        if engine.vector_store:
            from backend.project.indexer import ProjectIndexer
            indexer = ProjectIndexer(engine.vector_store)
            result = await indexer.index_project(".")
            print(f"   ✓ Indexed {result['files_indexed']} files, {result['chunks_created']} chunks")
        
        # 2. Generate code
        print("\n2. Generating code...")
        result = await engine.execute_task(
            task="Create a Python class for managing a todo list with add, remove, and list methods",
            agent_type="code_writer"
        )
        print(f"   ✓ Code generated: {len(result.get('code', ''))} characters")
        
        # 3. Research codebase
        print("\n3. Researching codebase...")
        result = await engine.execute_task(
            task="Analyze the project structure and identify main components",
            agent_type="research"
        )
        print(f"   ✓ Research completed: {len(result.get('report', ''))} characters")
        
        # 4. Analyze data (if data available)
        print("\n4. Data analysis example...")
        # This would require actual data file
        # result = await engine.execute_task(
        #     task="Perform EDA on dataset",
        #     agent_type="data_analysis",
        #     context={"data_path": "data.csv", "target_column": "target"}
        # )
        print("   ⚠ Skipped (no data file)")
        
        # 5. Use ReAct agent for complex task
        print("\n5. Using ReAct agent for complex task...")
        result = await engine.execute_task(
            task="Read the README.md file and create a summary",
            agent_type="react"
        )
        if result.get("success"):
            print(f"   ✓ Task completed in {result.get('iterations', 0)} iterations")
            print(f"   Answer: {result.get('final_answer', '')[:100]}...")
        
        # 6. Monitor system
        print("\n6. System monitoring...")
        result = await engine.execute_task(
            task="Check system performance and provide recommendations",
            agent_type="monitoring"
        )
        if result.get("current_metrics"):
            metrics = result["current_metrics"]
            print(f"   ✓ CPU: {metrics.get('cpu_percent', 0):.1f}%")
            print(f"   ✓ Memory: {metrics.get('memory_mb', 0):.1f} MB")
        
        # 7. List available tools
        print("\n7. Available tools...")
        if engine.tool_registry:
            tools = await engine.tool_registry.list_tools()
            print(f"   ✓ {len(tools)} tools available:")
            for name in list(tools.keys())[:5]:
                print(f"     - {name}")
        
        # 8. Check engine status
        print("\n8. Engine status...")
        status = engine.get_status()
        print(f"   ✓ Initialized: {status['initialized']}")
        print(f"   ✓ Components: {sum(status['components'].values())}/{len(status['components'])}")
        
        print("\n" + "=" * 60)
        print("Workflow completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())


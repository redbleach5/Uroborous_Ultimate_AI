"""
Workflow example - Using WorkflowAgent to execute complex workflows
"""

import asyncio
from backend.core.engine import IDAEngine
from backend.config import get_config


async def main():
    """Workflow execution example"""
    
    print("=" * 60)
    print("AILLM Workflow Example")
    print("=" * 60)
    
    # Initialize engine
    config = get_config()
    engine = IDAEngine(config)
    await engine.initialize()
    
    try:
        # Example 1: Simple workflow with multiple steps
        print("\n1. Executing simple workflow...")
        
        workflow = {
            "name": "code_generation_workflow",
            "steps": [
                {
                    "name": "analyze_requirements",
                    "type": "agent",
                    "agent_type": "research",
                    "task": "Analyze the requirements for a todo list application"
                },
                {
                    "name": "generate_code",
                    "type": "agent",
                    "agent_type": "code_writer",
                    "task": "Generate Python code for a todo list class based on the analysis",
                    "dependencies": ["analyze_requirements"]
                }
            ],
            "stop_on_error": True
        }
        
        result = await engine.execute_task(
            task="Execute workflow for creating a todo list application",
            agent_type="workflow",
            context={"workflow": workflow}
        )
        
        if result.get("success"):
            print(f"   ✓ Workflow completed: {result['workflow']}")
            print(f"   ✓ Steps executed: {result['steps_executed']}")
        else:
            print(f"   ✗ Workflow failed: {result.get('error')}")
        
        # Example 2: Workflow with tool usage
        print("\n2. Executing workflow with tools...")
        
        workflow2 = {
            "name": "file_operations_workflow",
            "steps": [
                {
                    "name": "read_file",
                    "type": "tool",
                    "tool_name": "read_file",
                    "input": {"file_path": "README.md"}
                },
                {
                    "name": "analyze_content",
                    "type": "agent",
                    "agent_type": "research",
                    "task": "Analyze the README.md content and provide a summary",
                    "dependencies": ["read_file"]
                }
            ]
        }
        
        result2 = await engine.execute_task(
            task="Execute file operations workflow",
            agent_type="workflow",
            context={"workflow": workflow2}
        )
        
        if result2.get("success"):
            print(f"   ✓ Workflow completed: {result2['workflow']}")
        else:
            print(f"   ✗ Workflow failed: {result2.get('error')}")
        
        # Example 3: Natural language workflow
        print("\n3. Executing natural language workflow...")
        
        result3 = await engine.execute_task(
            task="Create a workflow that: 1) Reads a Python file, 2) Analyzes it for security issues, 3) Generates a report",
            agent_type="workflow"
        )
        
        if result3.get("success"):
            print(f"   ✓ Natural language workflow completed")
            print(f"   ✓ Steps: {result3.get('steps_executed', 0)}")
        else:
            print(f"   ✗ Workflow failed: {result3.get('error')}")
        
        print("\n" + "=" * 60)
        print("Workflow examples completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())


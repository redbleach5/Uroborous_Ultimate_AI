#!/usr/bin/env python3
"""
Script to check syntax of all Python files in the project
"""

import ast
import os
import sys
from pathlib import Path

# Определяем корень проекта (на уровень выше scripts/)
PROJECT_ROOT = Path(__file__).parent.parent


def check_syntax(filepath):
    """Check syntax of a Python file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
            ast.parse(code)
        return None
    except SyntaxError as e:
        return f"{filepath}:{e.lineno}: {e.msg}"
    except Exception as e:
        return f"{filepath}: {str(e)}"


def main():
    """Main function"""
    errors = []
    checked = 0
    
    # Directories to check (относительно корня проекта)
    directories = ['backend', 'tests', 'examples']
    
    # Files to check (относительно корня проекта)
    files = ['run.py', 'setup.py']
    
    # Check directories
    for directory in directories:
        dir_path = PROJECT_ROOT / directory
        if not dir_path.exists():
            continue
        
        for root, dirs, files_list in os.walk(dir_path):
            # Skip cache and venv directories
            dirs[:] = [d for d in dirs if d not in ['__pycache__', '.venv', 'venv', 'node_modules']]
            
            for file in files_list:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    error = check_syntax(filepath)
                    if error:
                        errors.append(error)
                    checked += 1
    
    # Check individual files
    for file in files:
        file_path = PROJECT_ROOT / file
        if file_path.exists():
            error = check_syntax(file_path)
            if error:
                errors.append(error)
            checked += 1
    
    # Print results
    if errors:
        print("❌ Syntax errors found:")
        for error in errors:
            print(f"  {error}")
        print(f"\nChecked {checked} files, found {len(errors)} errors")
        sys.exit(1)
    else:
        print(f"✅ All {checked} Python files are syntactically correct!")
        sys.exit(0)


if __name__ == '__main__':
    main()


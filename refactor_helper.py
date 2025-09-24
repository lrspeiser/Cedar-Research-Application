#!/usr/bin/env python3
"""
Helper script to extract and organize code from main_impl_full.py
into smaller modules.
"""

import ast
import os
import re
from typing import List, Tuple, Dict, Set

def analyze_file(file_path: str) -> Dict[str, any]:
    """Analyze a Python file and extract its structure."""
    with open(file_path, 'r', encoding='utf-8') as f:
        source = f.read()
    
    tree = ast.parse(source)
    
    # Collect information
    imports = []
    functions = []
    classes = []
    routes = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                imports.append(name.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        elif isinstance(node, ast.FunctionDef):
            # Check if it's a route
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Attribute):
                    if hasattr(decorator, 'attr') and decorator.attr in ['get', 'post', 'put', 'delete', 'websocket']:
                        routes.append(node.name)
                        break
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
    
    # Get line numbers for each function/class
    function_lines = {}
    class_lines = {}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                function_lines[node.name] = (node.lineno, node.end_lineno)
        elif isinstance(node, ast.ClassDef):
            if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                class_lines[node.name] = (node.lineno, node.end_lineno)
    
    return {
        'imports': list(set(imports)),
        'functions': functions,
        'classes': classes,
        'routes': routes,
        'function_lines': function_lines,
        'class_lines': class_lines,
        'total_lines': len(source.split('\n'))
    }

def categorize_functions(functions: List[str]) -> Dict[str, List[str]]:
    """Categorize functions based on their names and patterns."""
    categories = {
        'llm': [],
        'database': [],
        'routes': [],
        'shell': [],
        'file_ops': [],
        'utils': [],
        'websocket': [],
        'logging': [],
        'html': [],
    }
    
    for func in functions:
        func_lower = func.lower()
        
        # LLM related
        if any(x in func_lower for x in ['llm', 'openai', 'anthropic', 'claude', 'gpt', '_ai_', 'classify']):
            categories['llm'].append(func)
        # Database related
        elif any(x in func_lower for x in ['_db', 'database', 'migrate', 'engine', '_project_', 'registry']):
            categories['database'].append(func)
        # Shell related
        elif any(x in func_lower for x in ['shell', 'job']):
            categories['shell'].append(func)
        # File operations
        elif any(x in func_lower for x in ['file', 'upload', 'download', '_save_']):
            categories['file_ops'].append(func)
        # WebSocket related
        elif any(x in func_lower for x in ['ws_', 'websocket', 'socket']):
            categories['websocket'].append(func)
        # Logging related
        elif any(x in func_lower for x in ['log', '_log_']):
            categories['logging'].append(func)
        # HTML/Layout related
        elif any(x in func_lower for x in ['html', 'layout', 'render']):
            categories['html'].append(func)
        # Routes (API endpoints)
        elif func.startswith('api_') or func.startswith('view_'):
            categories['routes'].append(func)
        # General utilities
        else:
            categories['utils'].append(func)
    
    return categories

def main():
    file_path = '/Users/leonardspeiser/Projects/cedarpy/cedar_app/main_impl_full.py'
    
    print("Analyzing main_impl_full.py...")
    analysis = analyze_file(file_path)
    
    print(f"\n📊 File Statistics:")
    print(f"  Total lines: {analysis['total_lines']}")
    print(f"  Functions: {len(analysis['functions'])}")
    print(f"  Classes: {len(analysis['classes'])}")
    print(f"  Routes: {len(analysis['routes'])}")
    
    print(f"\n📦 Classes found:")
    for cls in analysis['classes']:
        lines = analysis['class_lines'].get(cls, (0, 0))
        print(f"  - {cls} (lines {lines[0]}-{lines[1]})")
    
    categories = categorize_functions(analysis['functions'])
    
    print(f"\n🗂️ Function Categories:")
    for cat, funcs in categories.items():
        if funcs:
            print(f"\n  {cat.upper()} ({len(funcs)} functions):")
            for func in funcs[:5]:  # Show first 5
                lines = analysis['function_lines'].get(func, (0, 0))
                print(f"    - {func} (lines {lines[0]}-{lines[1]})")
            if len(funcs) > 5:
                print(f"    ... and {len(funcs) - 5} more")
    
    # Find largest functions
    print(f"\n📏 Largest Functions (by line count):")
    func_sizes = [(name, end - start) for name, (start, end) in analysis['function_lines'].items()]
    func_sizes.sort(key=lambda x: x[1], reverse=True)
    for name, size in func_sizes[:10]:
        lines = analysis['function_lines'][name]
        print(f"  - {name}: {size} lines (lines {lines[0]}-{lines[1]})")

if __name__ == "__main__":
    main()
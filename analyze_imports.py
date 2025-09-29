#!/usr/bin/env python3
"""
Analyze all imports in the Cedar project to identify potential issues
"""

import os
import ast
import sys
from pathlib import Path
from typing import List, Dict, Set, Tuple
import json

class ImportAnalyzer:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.imports = {}  # file -> list of imports
        self.module_exists = {}  # cache for module existence checks
        self.issues = []
        
        # Known module mappings after refactoring
        self.known_refactorings = {
            'cedar_orchestrator.advanced_orchestrator': 'cedar_orchestrator.orchestrator',
            'cedar_app.main_impl_full': None,  # Deleted
            'cedar_app.main_impl_full_refactored': None,  # Deleted
            'cedar_tools_modules': 'cedar_tools',  # Consolidated
        }
        
        # Directories to skip
        self.skip_dirs = {
            '.git', '__pycache__', '.venv', 'venv', 'env', 
            'node_modules', 'dist', 'build', '.pytest_cache',
            'packaging', 'lib', 'site-packages'
        }
        
    def analyze(self):
        """Main analysis function"""
        print("Analyzing imports in Cedar project...")
        print("=" * 80)
        
        # Collect all Python files
        python_files = self.collect_python_files()
        print(f"Found {len(python_files)} Python files to analyze\n")
        
        # Analyze each file
        for file_path in python_files:
            self.analyze_file(file_path)
        
        # Generate report
        self.generate_report()
        
    def collect_python_files(self) -> List[Path]:
        """Collect all Python files in the project"""
        files = []
        for root, dirs, filenames in os.walk(self.project_root):
            # Skip directories
            dirs[:] = [d for d in dirs if d not in self.skip_dirs]
            
            for filename in filenames:
                if filename.endswith('.py'):
                    files.append(Path(root) / filename)
        
        return sorted(files)
    
    def analyze_file(self, file_path: Path):
        """Analyze imports in a single file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append({
                            'type': 'import',
                            'module': alias.name,
                            'alias': alias.asname,
                            'line': node.lineno
                        })
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    level = node.level  # Number of dots for relative imports
                    
                    # Handle relative imports
                    if level > 0:
                        # Convert relative to absolute for checking
                        module = self.resolve_relative_import(file_path, module, level)
                    
                    for alias in node.names:
                        imports.append({
                            'type': 'from',
                            'module': module,
                            'name': alias.name,
                            'alias': alias.asname,
                            'line': node.lineno,
                            'relative': level > 0
                        })
            
            # Store imports for this file
            rel_path = file_path.relative_to(self.project_root)
            self.imports[str(rel_path)] = imports
            
            # Check each import
            for imp in imports:
                self.check_import(rel_path, imp)
                
        except Exception as e:
            print(f"Error analyzing {file_path}: {e}")
    
    def resolve_relative_import(self, file_path: Path, module: str, level: int) -> str:
        """Convert relative import to absolute"""
        # Get the package path of the current file
        package_parts = file_path.relative_to(self.project_root).parts[:-1]
        
        # Go up 'level' directories
        if level <= len(package_parts):
            base_parts = package_parts[:len(package_parts) - level + 1]
        else:
            base_parts = []
        
        # Add the module part if it exists
        if module:
            full_parts = list(base_parts) + module.split('.')
        else:
            full_parts = list(base_parts)
        
        return '.'.join(full_parts)
    
    def check_import(self, file_path: Path, imp: dict):
        """Check if an import is valid and correct"""
        module = imp['module']
        
        # Skip standard library and common third-party imports
        if self.is_standard_or_third_party(module):
            return
        
        # Check for known refactored modules
        if module in self.known_refactorings:
            correct = self.known_refactorings[module]
            if correct:
                self.issues.append({
                    'file': str(file_path),
                    'line': imp['line'],
                    'issue': 'outdated_import',
                    'module': module,
                    'should_be': correct,
                    'severity': 'error'
                })
            else:
                self.issues.append({
                    'file': str(file_path),
                    'line': imp['line'],
                    'issue': 'deleted_module',
                    'module': module,
                    'severity': 'error'
                })
            return
        
        # Check if module exists in project
        if module.startswith('cedar'):
            if not self.module_exists_in_project(module):
                # Check if it's trying to import a specific class that moved
                self.check_moved_classes(file_path, imp)
    
    def check_moved_classes(self, file_path: Path, imp: dict):
        """Check for imports of classes that have moved"""
        # Known class movements after refactoring
        moved_classes = {
            'ShellAgent': 'cedar_orchestrator.execution_agents',
            'CodeAgent': 'cedar_orchestrator.execution_agents',
            'SQLAgent': 'cedar_orchestrator.execution_agents',
            'AgentResult': 'cedar_orchestrator.execution_agents',
            'MathAgent': 'cedar_orchestrator.specialized_agents',
            'ResearchAgent': 'cedar_orchestrator.specialized_agents',
            'StrategyAgent': 'cedar_orchestrator.specialized_agents',
            'DataAgent': 'cedar_orchestrator.specialized_agents',
            'NotesAgent': 'cedar_orchestrator.specialized_agents',
            'FileAgent': 'cedar_orchestrator.specialized_agents',
            'ImageCreationAgent': 'cedar_orchestrator.specialized_agents',
            'ImageAnalysisAgent': 'cedar_orchestrator.specialized_agents',
            'ChiefAgent': 'cedar_orchestrator.orchestrator',
            'ThinkerOrchestrator': 'cedar_orchestrator.orchestrator',
        }
        
        if imp.get('name') in moved_classes:
            correct_module = moved_classes[imp['name']]
            if imp['module'] != correct_module:
                self.issues.append({
                    'file': str(file_path),
                    'line': imp['line'],
                    'issue': 'wrong_module_for_class',
                    'class': imp['name'],
                    'current_module': imp['module'],
                    'should_be': correct_module,
                    'severity': 'warning'
                })
    
    def module_exists_in_project(self, module: str) -> bool:
        """Check if a module exists in the project"""
        if module in self.module_exists:
            return self.module_exists[module]
        
        # Convert module path to file path
        parts = module.split('.')
        
        # Check as a package (directory with __init__.py)
        package_path = self.project_root / Path(*parts)
        if package_path.is_dir() and (package_path / '__init__.py').exists():
            self.module_exists[module] = True
            return True
        
        # Check as a module (file.py)
        if parts:
            module_file = self.project_root / Path(*parts[:-1]) / f"{parts[-1]}.py"
            if module_file.exists():
                self.module_exists[module] = True
                return True
        
        self.module_exists[module] = False
        return False
    
    def is_standard_or_third_party(self, module: str) -> bool:
        """Check if module is standard library or common third-party"""
        if not module:
            return False
            
        first_part = module.split('.')[0]
        
        # Standard library modules
        stdlib = {
            'os', 'sys', 'json', 'time', 'datetime', 'pathlib', 'typing',
            'asyncio', 'logging', 'unittest', 'subprocess', 'tempfile',
            're', 'collections', 'itertools', 'functools', 'hashlib',
            'random', 'math', 'statistics', 'urllib', 'http', 'socket',
            'sqlite3', 'csv', 'io', 'base64', 'uuid', 'copy', 'shutil',
            'ast', 'inspect', 'traceback', 'warnings', 'contextlib',
            'multiprocessing', 'threading', 'queue', 'enum', 'abc',
            'importlib', 'pkgutil', 'platform', 'glob', 'fnmatch'
        }
        
        # Common third-party modules
        third_party = {
            'fastapi', 'uvicorn', 'starlette', 'pydantic', 'sqlalchemy',
            'openai', 'requests', 'numpy', 'pandas', 'pytest', 'websockets',
            'aiofiles', 'httpx', 'websocket', 'jinja2', 'click', 'rich',
            'python-dotenv', 'PyQt5', 'PIL', 'Pillow', 'tiktoken',
            'pytesseract', 'pdf2image', 'pdfplumber', 'pypdf', 'PyPDF2',
            'matplotlib', 'seaborn', 'plotly', 'scipy', 'sklearn'
        }
        
        return first_part in stdlib or first_part in third_party
    
    def generate_report(self):
        """Generate the import analysis report"""
        print("\n" + "=" * 80)
        print("IMPORT ANALYSIS REPORT")
        print("=" * 80)
        
        # Group imports by file
        total_imports = 0
        cedar_imports = 0
        
        print("\n## All Files and Their Imports\n")
        
        for file_path, imports in sorted(self.imports.items()):
            if not imports:
                continue
                
            # Filter to Cedar-specific imports
            cedar_file_imports = [
                imp for imp in imports 
                if imp['module'].startswith('cedar') or 
                   imp['module'].startswith('agents') or
                   imp['module'].startswith('main') or
                   imp['module'].startswith('test')
            ]
            
            if cedar_file_imports:
                print(f"\n### {file_path}")
                for imp in cedar_file_imports:
                    total_imports += 1
                    cedar_imports += 1
                    
                    if imp['type'] == 'import':
                        print(f"  Line {imp['line']:4}: import {imp['module']}")
                    else:
                        rel = " (relative)" if imp.get('relative') else ""
                        print(f"  Line {imp['line']:4}: from {imp['module']} import {imp['name']}{rel}")
        
        # Report issues
        if self.issues:
            print("\n" + "=" * 80)
            print("ISSUES FOUND")
            print("=" * 80)
            
            # Group by severity
            errors = [i for i in self.issues if i['severity'] == 'error']
            warnings = [i for i in self.issues if i['severity'] == 'warning']
            
            if errors:
                print(f"\n## ERRORS ({len(errors)} found) - These need immediate fixing:\n")
                for issue in errors:
                    print(f"❌ {issue['file']}:{issue['line']}")
                    if issue['issue'] == 'outdated_import':
                        print(f"   Import '{issue['module']}' should be '{issue['should_be']}'")
                    elif issue['issue'] == 'deleted_module':
                        print(f"   Import '{issue['module']}' - this module has been deleted!")
                    print()
            
            if warnings:
                print(f"\n## WARNINGS ({len(warnings)} found) - Potential issues:\n")
                for issue in warnings:
                    print(f"⚠️  {issue['file']}:{issue['line']}")
                    if issue['issue'] == 'wrong_module_for_class':
                        print(f"   Class '{issue['class']}' imported from '{issue['current_module']}'")
                        print(f"   Should be imported from '{issue['should_be']}'")
                    print()
        else:
            print("\n✅ No import issues found!")
        
        # Summary statistics
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total Python files analyzed: {len(self.imports)}")
        print(f"Total Cedar-specific imports: {cedar_imports}")
        print(f"Issues found: {len(self.issues)}")
        if self.issues:
            errors = len([i for i in self.issues if i['severity'] == 'error'])
            warnings = len([i for i in self.issues if i['severity'] == 'warning'])
            print(f"  - Errors: {errors}")
            print(f"  - Warnings: {warnings}")

if __name__ == "__main__":
    analyzer = ImportAnalyzer(os.path.dirname(os.path.abspath(__file__)))
    analyzer.analyze()
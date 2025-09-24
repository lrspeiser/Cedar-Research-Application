#!/usr/bin/env python3
"""
Script to extract and organize code from main_impl_full.py into smaller modules.
This will create the modular structure needed.
"""

import os
import re

def extract_imports(lines: list) -> tuple:
    """Extract import statements from lines."""
    imports = []
    other = []
    in_imports = True
    
    for line in lines:
        stripped = line.strip()
        if in_imports:
            if stripped.startswith(('import ', 'from ')) or not stripped or stripped.startswith('#'):
                imports.append(line)
            else:
                in_imports = False
                other.append(line)
        else:
            other.append(line)
    
    return imports, other

def read_file():
    """Read the main file."""
    with open('/Users/leonardspeiser/Projects/cedarpy/cedar_app/main_impl_full.py', 'r') as f:
        return f.readlines()

def extract_section(lines: list, start_line: int, end_line: int) -> list:
    """Extract a section of lines."""
    return lines[start_line-1:end_line]

def write_module(path: str, content: str):
    """Write a module file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)
    print(f"Created: {path}")

def main():
    lines = read_file()
    base_path = '/Users/leonardspeiser/Projects/cedarpy/cedar_app'
    
    # Extract the layout function and related HTML generation
    print("\nExtracting HTML utilities...")
    html_content = '''"""
HTML utilities module for Cedar app.
Contains layout functions and HTML generation helpers.
"""

import os
import html
from typing import Optional, Dict, Any
from datetime import datetime

def escape(s: str) -> str:
    """Escape HTML special characters."""
    return html.escape(s, quote=True)

'''
    # Extract layout function (lines 1410-1612)
    html_content += ''.join(extract_section(lines, 1410, 1612))
    
    # Extract other HTML functions
    html_content += '\n\n'
    html_content += ''.join(extract_section(lines, 2160, 2206))  # projects_list_html
    html_content += '\n\n'
    # Note: project_page_html is too large (1562 lines), we'll need to handle it specially
    
    write_module(f'{base_path}/utils/html.py', html_content)
    
    # Extract Shell-related functions
    print("\nExtracting Shell module...")
    shell_content = '''"""
Shell execution module for Cedar app.
Handles shell command execution and job management.
"""

import os
import sys
import uuid
import queue
import signal
import subprocess
import threading
import asyncio
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from collections import deque

from cedar_app.config import LOGS_DIR, SHELL_DEFAULT_WORKDIR

'''
    
    # Extract ShellJob class and related functions
    shell_content += ''.join(extract_section(lines, 3777, 3818))  # ShellJob class
    shell_content += '\n\n'
    shell_content += '# Shell job management\n'
    shell_content += '_shell_jobs: Dict[str, Any] = {}\n'
    shell_content += '_shell_jobs_lock = threading.Lock()\n\n'
    shell_content += ''.join(extract_section(lines, 3821, 3937))  # _run_job
    shell_content += '\n\n'
    shell_content += ''.join(extract_section(lines, 3944, 3955))  # start_shell_job and get_shell_job
    
    write_module(f'{base_path}/tools/shell.py', shell_content)
    
    # Extract LLM utilities
    print("\nExtracting LLM client module...")
    llm_content = '''"""
LLM client module for Cedar app.
Handles LLM client configuration and classification.
"""

import os
from typing import Optional, Tuple, Dict, Any

'''
    
    # Extract LLM configuration function
    llm_content += ''.join(extract_section(lines, 572, 716))  # _llm_client_config
    llm_content += '\n\n'
    llm_content += ''.join(extract_section(lines, 719, 794))  # _llm_classify_file
    
    write_module(f'{base_path}/llm/client.py', llm_content)
    
    # Extract logging utilities
    print("\nExtracting logging module...")
    logging_content = '''"""
Logging utilities module for Cedar app.
Handles unified logging and client log ingestion.
"""

import os
import sys
import time as _time
import logging as _logging
import builtins as _bi
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import deque
from contextvars import ContextVar

from fastapi import Request
from pydantic import BaseModel

# Global logging buffers
_LOG_BUFFER = deque(maxlen=1000)
_SERVER_LOG_BUFFER = deque(maxlen=1000)
_current_path: ContextVar[str] = ContextVar('current_path', default='')

'''
    
    # Extract CedarBufferHandler class
    logging_content += ''.join(extract_section(lines, 4936, 4962))
    logging_content += '\n\n'
    # Extract logging installation function
    logging_content += ''.join(extract_section(lines, 4964, 5039))
    logging_content += '\n\n'
    # Extract ClientLogEntry class
    logging_content += ''.join(extract_section(lines, 5048, 5057))
    
    write_module(f'{base_path}/utils/logging.py', logging_content)
    
    # Create __init__ files for packages
    print("\nCreating __init__.py files...")
    for dir_path in ['llm', 'tools', 'routes', 'utils']:
        init_path = f'{base_path}/{dir_path}/__init__.py'
        if not os.path.exists(init_path):
            write_module(init_path, '"""Package initialization."""\n')
    
    print("\n✅ Initial module extraction complete!")
    print("\n⚠️  Note: main_impl_full.py still contains large functions that need to be broken down:")
    print("  - project_page_html (1562 lines) - needs to be split into smaller template functions")
    print("  - ask_orchestrator (364 lines) - should be in orchestrator module")
    print("  - Several route handlers that should be in routes/*.py")
    print("\nNext steps:")
    print("  1. Continue extracting remaining functions")
    print("  2. Update imports in all files")
    print("  3. Create main.py to initialize FastAPI app")
    print("  4. Test the refactored application")
    print("  5. Delete main_impl_full.py")

if __name__ == "__main__":
    main()
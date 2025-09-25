#!/usr/bin/env python3
"""
Extract SQL-related route functions from main_impl_full.py into a separate sql_routes.py module.

This script:
1. Reads main_impl_full.py
2. Extracts SQL-related functions (ws_sqlx, make_table_branch_aware, undo_last_sql, execute_sql)
3. Creates routes/sql_routes.py with these functions
4. Updates main_impl_full.py to import from the new module
"""

import os
import sys
from pathlib import Path

# Add parent directory to path to import modules
cedar_app_dir = Path(__file__).parent.parent
sys.path.insert(0, str(cedar_app_dir))

def extract_sql_routes():
    """Extract SQL routes from main_impl_full.py."""
    
    # Read the original file
    main_impl_path = cedar_app_dir / "main_impl_full.py"
    with open(main_impl_path, 'r') as f:
        lines = f.readlines()
    
    # Define the SQL functions to extract with their line ranges
    sql_functions = [
        {
            'name': 'ws_sqlx',
            'start': 836,  # Line 837 minus 1 for 0-based indexing
            'end': 1012,
            'decorator': '@app.websocket("/ws/sqlx")',
            'signature': 'async def ws_sqlx(websocket: WebSocket)',
        },
        {
            'name': 'make_table_branch_aware',
            'start': 1417,  # Line 1418 minus 1
            'end': 1492,
            'decorator': '@app.post("/make_table_branch_aware/{table_name}")',
            'signature': 'async def make_table_branch_aware(table_name: str, request: Request)',
        },
        {
            'name': 'undo_last_sql',
            'start': 1499,  # Line 1500 minus 1
            'end': 1584,
            'decorator': '@app.post("/undo_last_sql")',
            'signature': 'async def undo_last_sql(request: Request)',
        },
        {
            'name': 'execute_sql',
            'start': 1584,  # Line 1585 minus 1
            'end': 1658,
            'decorator': '@app.post("/execute_sql")',
            'signature': 'async def execute_sql(request: Request)',
        }
    ]
    
    # Create the routes directory if it doesn't exist
    routes_dir = cedar_app_dir / "routes"
    routes_dir.mkdir(exist_ok=True)
    
    # Generate sql_routes.py content
    sql_routes_content = '''"""
SQL-related route handlers extracted from main_impl_full.py.

This module contains WebSocket and HTTP endpoints for SQL operations including:
- SQL execution via WebSocket
- Branch-aware table modifications
- SQL undo functionality
- Direct SQL execution
"""

from __future__ import annotations

import json
import traceback
import asyncio
from typing import Optional, Dict, Any, List

from fastapi import WebSocket, Request, HTTPException
from fastapi.responses import JSONResponse
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.orm import Session

# Import shared dependencies from main_impl_full
from cedar_app.main_impl_full import (
    app,
    get_project_db,
    _get_project_engine,
    ensure_project_initialized,
    Branch,
    Thread,
    ThreadMessage,
    SQLUndoLog,
    Setting,
    logger,
    record_changelog,
    run_ai_command,
    BRANCH_AWARE_MODELS,
)


'''
    
    # Extract each function
    for func_info in sql_functions:
        # Get the function code
        func_lines = lines[func_info['start']:func_info['end']]
        
        # Add the function to sql_routes.py
        sql_routes_content += f"{func_info['decorator']}\n"
        sql_routes_content += ''.join(func_lines) + '\n\n'
    
    # Write the sql_routes.py file
    sql_routes_path = routes_dir / "sql_routes.py"
    with open(sql_routes_path, 'w') as f:
        f.write(sql_routes_content)
    
    print(f"Created {sql_routes_path}")
    
    # Now update main_impl_full.py to remove these functions and import them
    
    # Build new main_impl_full.py content
    new_lines = []
    
    # Add import statement near the top (after other imports)
    import_added = False
    
    i = 0
    while i < len(lines):
        # Skip the SQL function definitions
        skip = False
        for func_info in sql_functions:
            if i >= func_info['start'] and i < func_info['end']:
                skip = True
                # If we're at the start of this function, skip to the end
                if i == func_info['start']:
                    i = func_info['end']
                    continue
        
        if not skip:
            # Add import after the app creation but before routes
            if not import_added and 'app = FastAPI(' in lines[i]:
                new_lines.append(lines[i])
                # Add a few more lines to get past the app configuration
                while i < len(lines) - 1 and not lines[i+1].strip().startswith('@'):
                    i += 1
                    new_lines.append(lines[i])
                # Now add the import
                new_lines.append('\n')
                new_lines.append('# Import SQL routes\n')
                new_lines.append('from cedar_app.routes import sql_routes\n')
                new_lines.append('\n')
                import_added = True
                i += 1
                continue
            
            new_lines.append(lines[i])
        
        i += 1
    
    # Write the updated main_impl_full.py
    with open(main_impl_path, 'w') as f:
        f.writelines(new_lines)
    
    print(f"Updated {main_impl_path}")
    print(f"Removed {sum(func['end'] - func['start'] for func in sql_functions)} lines")
    print(f"New file has {len(new_lines)} lines (was {len(lines)} lines)")
    
    return True

if __name__ == "__main__":
    try:
        if extract_sql_routes():
            print("\n✅ Successfully extracted SQL routes!")
            print("\nThe SQL-related functions have been moved to routes/sql_routes.py")
            print("main_impl_full.py has been updated to import from the new module")
        else:
            print("\n❌ Extraction failed")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
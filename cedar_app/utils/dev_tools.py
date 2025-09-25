"""
Development and testing tools for Cedar app.
Provides tool execution endpoint for testing LLM tools and utilities.
"""

import os
import json
import base64
import subprocess
import tempfile
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from ..config import SHELL_API_ENABLED, SHELL_API_TOKEN
from ..shell_utils import is_local_request as _is_local_request


class ToolExecRequest(BaseModel):
    """Request model for tool execution API."""
    tool: str
    args: Optional[Dict[str, Any]] = None


def api_test_tool_exec(body: ToolExecRequest, request: Request):
    """
    Execute a tool for testing purposes.
    Only available when shell API is enabled and request is authenticated.
    Supports: search_files, search_codebase, run_command, save_file.
    """
    # Security check: require shell API enabled and token auth
    if not SHELL_API_ENABLED:
        raise HTTPException(status_code=403, detail="Shell API not enabled")
    
    # Check authorization
    auth_header = request.headers.get("Authorization", "")
    x_api_token = request.headers.get("X-API-Token", "")
    
    # Check for Bearer token
    valid_auth = False
    if auth_header.startswith("Bearer ") and SHELL_API_TOKEN:
        provided_token = auth_header[7:]
        if provided_token == SHELL_API_TOKEN:
            valid_auth = True
    
    # Check for X-API-Token
    if x_api_token and SHELL_API_TOKEN:
        if x_api_token == SHELL_API_TOKEN:
            valid_auth = True
    
    # Allow local requests without token (for development)
    if _is_local_request(request) and not SHELL_API_TOKEN:
        valid_auth = True
    
    if not valid_auth:
        raise HTTPException(status_code=401, detail="Invalid or missing authentication")
    
    tool_name = body.tool
    args = body.args or {}
    
    # Tool implementations
    if tool_name == "search_files":
        # Search for files by name pattern
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        max_results = args.get("max_results", 100)
        
        if not pattern:
            return JSONResponse({
                "success": False,
                "error": "Pattern required for search_files"
            })
        
        try:
            # Use find command
            result = subprocess.run(
                ["find", path, "-type", "f", "-name", pattern],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            files = result.stdout.strip().split("\n") if result.stdout.strip() else []
            files = files[:max_results]
            
            return JSONResponse({
                "success": True,
                "files": files,
                "count": len(files)
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": str(e)
            })
    
    elif tool_name == "search_codebase":
        # Search code content
        query = args.get("query", "")
        path = args.get("path", ".")
        file_pattern = args.get("file_pattern", "*")
        max_results = args.get("max_results", 50)
        
        if not query:
            return JSONResponse({
                "success": False,
                "error": "Query required for search_codebase"
            })
        
        try:
            # Use grep with find
            result = subprocess.run(
                f"find {path} -name '{file_pattern}' -type f -exec grep -l '{query}' {{}} \\;",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            files = result.stdout.strip().split("\n") if result.stdout.strip() else []
            files = files[:max_results]
            
            # Get matches with context
            matches = []
            for f in files[:10]:  # Limit detailed matches
                grep_result = subprocess.run(
                    ["grep", "-n", "-B1", "-A1", query, f],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if grep_result.stdout:
                    matches.append({
                        "file": f,
                        "matches": grep_result.stdout[:500]
                    })
            
            return JSONResponse({
                "success": True,
                "files": files,
                "matches": matches,
                "count": len(files)
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": str(e)
            })
    
    elif tool_name == "run_command":
        # Execute shell command
        command = args.get("command", "")
        cwd = args.get("cwd", None)
        timeout = args.get("timeout", 30)
        
        if not command:
            return JSONResponse({
                "success": False,
                "error": "Command required for run_command"
            })
        
        # Security: limit dangerous commands
        dangerous_patterns = ["rm -rf", "dd if=", "mkfs", "format", ">", ">>"]
        for pattern in dangerous_patterns:
            if pattern in command:
                return JSONResponse({
                    "success": False,
                    "error": f"Command contains potentially dangerous pattern: {pattern}"
                })
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout
            )
            
            return JSONResponse({
                "success": result.returncode == 0,
                "stdout": result.stdout[:10000],  # Limit output size
                "stderr": result.stderr[:10000],
                "returncode": result.returncode
            })
        except subprocess.TimeoutExpired:
            return JSONResponse({
                "success": False,
                "error": f"Command timed out after {timeout} seconds"
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": str(e)
            })
    
    elif tool_name == "save_file":
        # Save content to a file
        path = args.get("path", "")
        content = args.get("content", "")
        encoding = args.get("encoding", "utf-8")
        create_dirs = args.get("create_dirs", True)
        
        if not path:
            return JSONResponse({
                "success": False,
                "error": "Path required for save_file"
            })
        
        # Security: prevent writing to sensitive locations
        forbidden_dirs = ["/etc", "/sys", "/proc", "/boot", "/usr", "/bin", "/sbin"]
        for forbidden in forbidden_dirs:
            if path.startswith(forbidden):
                return JSONResponse({
                    "success": False,
                    "error": f"Cannot write to system directory: {forbidden}"
                })
        
        try:
            # Create directories if needed
            if create_dirs:
                os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # Handle base64 encoded content
            if args.get("base64"):
                content = base64.b64decode(content)
                with open(path, "wb") as f:
                    f.write(content)
            else:
                with open(path, "w", encoding=encoding) as f:
                    f.write(content)
            
            return JSONResponse({
                "success": True,
                "path": path,
                "size": len(content)
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": str(e)
            })
    
    elif tool_name == "read_file":
        # Read file content
        path = args.get("path", "")
        encoding = args.get("encoding", "utf-8")
        lines = args.get("lines", None)
        
        if not path:
            return JSONResponse({
                "success": False,
                "error": "Path required for read_file"
            })
        
        try:
            if not os.path.exists(path):
                return JSONResponse({
                    "success": False,
                    "error": f"File not found: {path}"
                })
            
            with open(path, "r", encoding=encoding) as f:
                if lines:
                    content = "".join(f.readlines()[:lines])
                else:
                    content = f.read()
            
            # Limit size
            if len(content) > 100000:
                content = content[:100000] + "\n... (truncated)"
            
            return JSONResponse({
                "success": True,
                "path": path,
                "content": content,
                "size": os.path.getsize(path)
            })
        except Exception as e:
            return JSONResponse({
                "success": False,
                "error": str(e)
            })
    
    else:
        return JSONResponse({
            "success": False,
            "error": f"Unknown tool: {tool_name}",
            "available_tools": [
                "search_files",
                "search_codebase",
                "run_command",
                "save_file",
                "read_file"
            ]
        })
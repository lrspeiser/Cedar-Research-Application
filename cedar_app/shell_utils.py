"""
Shell Utilities for Cedar
=========================

This module contains all shell/terminal execution functionality including:
- Shell job management
- WebSocket handlers for shell streaming
- Security helpers for shell API
- Shell UI generation
"""

import os
import uuid
import queue
import signal
import threading
import subprocess
import platform
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import Request, Header, HTTPException, WebSocket
from fastapi.responses import HTMLResponse
from starlette.websockets import WebSocketDisconnect
from pydantic import BaseModel


class ShellJob:
    """Represents a shell job execution with output streaming."""
    
    def __init__(self, script: str, shell_path: Optional[str] = None, trace_x: bool = False, 
                 workdir: Optional[str] = None, logs_dir: str = None, default_workdir: str = None):
        self.id = uuid.uuid4().hex
        self.script = script
        # Preserve requested shell_path if provided; resolution and fallbacks happen at run-time
        self.shell_path = shell_path or os.environ.get("SHELL")
        self.trace_x = bool(trace_x)
        self.workdir = workdir or default_workdir
        self.start_time = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None
        self.status = "starting"  # starting|running|finished|error|killed
        self.return_code: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.output_lines: List[str] = []
        
        # Create log path if logs_dir provided
        if logs_dir:
            self.log_path = os.path.join(logs_dir, f"{self.start_time.strftime('%Y%m%dT%H%M%SZ')}__{self.id}.log")
        else:
            self.log_path = None
        self._lock = threading.Lock()

    def append_line(self, line: str):
        """Append a line to output, log file, and queue."""
        if self.log_path:
            try:
                with open(self.log_path, "a", encoding="utf-8", errors="replace") as lf:
                    lf.write(line)
            except Exception:
                pass
        with self._lock:
            self.output_lines.append(line)
        try:
            self.queue.put_nowait(line)
        except Exception:
            pass

    def kill(self):
        """Kill the shell job process."""
        with self._lock:
            if self.proc and self.status in ("starting", "running"):
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                except Exception:
                    try:
                        self.proc.terminate()
                    except Exception:
                        pass
                self.status = "killed"


def run_shell_job(job: ShellJob):
    """Execute a shell job in a subprocess."""
    
    def _is_executable(p: Optional[str]) -> bool:
        try:
            return bool(p) and os.path.isfile(p) and os.access(p, os.X_OK)
        except Exception:
            return False

    def _candidate_shells(requested: Optional[str]) -> List[str]:
        cands: List[str] = []
        if requested and requested not in cands:
            cands.append(requested)
        env_shell = os.environ.get("SHELL")
        if env_shell and env_shell not in cands:
            cands.append(env_shell)
        # macOS default first when applicable
        if platform.system().lower() == "darwin" and "/bin/zsh" not in cands:
            cands.append("/bin/zsh")
        for p in ("/bin/bash", "/bin/sh"):
            if p not in cands:
                cands.append(p)
        return cands

    def _args_for(shell_path: str, script: str) -> List[str]:
        base = os.path.basename(shell_path)
        # bash/zsh/ksh/fish accept -l -c; sh/dash typically support only -c
        if base in {"bash", "zsh", "ksh", "fish"}:
            return ["-lc", script]
        return ["-c", script]

    # Resolve shell with fallbacks and emit helpful context
    candidates = _candidate_shells(job.shell_path)
    resolved: Optional[str] = None
    for p in candidates:
        if _is_executable(p):
            resolved = p
            break

    if not resolved:
        job.status = "error"
        job.end_time = datetime.utcnow()
        job.append_line(f"[shell-resolve-error] none executable among: {', '.join(candidates)}\n")
        try:
            job.queue.put_nowait("__CEDARPY_EOF__\n")
        except Exception:
            pass
        return

    # Optionally enable shell xtrace to echo commands as they are executed
    effective_script = job.script
    try:
        base_shell = os.path.basename(resolved)
    except Exception:
        base_shell = ''
    if job.trace_x:
        if base_shell in {"bash", "zsh", "ksh", "sh"}:
            effective_script = "set -x; " + effective_script
        else:
            # Non-POSIX shells may not support set -x; we note this and continue without it
            job.append_line(f"[trace] requested but not supported for shell={base_shell}\n")
    args = _args_for(resolved, effective_script)

    # Start process group so Stop can kill descendants
    job.status = "running"
    # Emit startup context to both UI and log file
    job.append_line(f"[start] job_id={job.id} at={datetime.utcnow().isoformat()}Z\n")
    job.append_line(f"[using-shell] path={resolved} args={' '.join(args[:-1])} (script length={len(job.script)} chars)\n")
    if job.trace_x:
        job.append_line("[trace] set -x enabled\n")
    job.append_line(f"[cwd] {job.workdir}\n")
    if job.log_path:
        job.append_line(f"[log] {job.log_path}\n")

    try:
        # Ensure workdir exists
        try:
            os.makedirs(job.workdir, exist_ok=True)
        except Exception:
            pass
        job.proc = subprocess.Popen(
            [resolved] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid,
            env=os.environ.copy(),
            cwd=job.workdir,
        )
    except Exception as e:
        job.status = "error"
        job.end_time = datetime.utcnow()
        job.append_line(f"[spawn-error] {type(e).__name__}: {e}\n")
        try:
            job.queue.put_nowait("__CEDARPY_EOF__\n")
        except Exception:
            pass
        return

    # Stream output
    try:
        assert job.proc and job.proc.stdout is not None
        for line in job.proc.stdout:
            job.append_line(line)
    except Exception as e:
        job.append_line(f"[stream-error] {type(e).__name__}: {e}\n")
    finally:
        if job.proc:
            job.proc.wait()
            job.return_code = job.proc.returncode
        job.end_time = datetime.utcnow()
        if job.status != "killed":
            job.status = "finished" if (job.return_code == 0) else "error"
        # Signal end of stream
        try:
            job.queue.put_nowait("__CEDARPY_EOF__\n")
        except Exception:
            pass


class ShellJobManager:
    """Manages shell job instances."""
    
    def __init__(self, logs_dir: str = None, default_workdir: str = None):
        self.jobs: Dict[str, ShellJob] = {}
        self.lock = threading.Lock()
        self.logs_dir = logs_dir
        self.default_workdir = default_workdir or os.getcwd()
    
    def start_job(self, script: str, shell_path: Optional[str] = None, 
                  trace_x: bool = False, workdir: Optional[str] = None) -> ShellJob:
        """Start a new shell job."""
        job = ShellJob(script=script, shell_path=shell_path, trace_x=trace_x, 
                      workdir=workdir, logs_dir=self.logs_dir, 
                      default_workdir=self.default_workdir)
        with self.lock:
            self.jobs[job.id] = job
        t = threading.Thread(target=run_shell_job, args=(job,), daemon=True)
        t.start()
        return job
    
    def get_job(self, job_id: str) -> Optional[ShellJob]:
        """Get a shell job by ID."""
        with self.lock:
            return self.jobs.get(job_id)


class ShellRunRequest(BaseModel):
    """Request model for shell run API."""
    script: str
    shell_path: Optional[str] = None
    trace_x: Optional[bool] = None
    workdir_mode: Optional[str] = None  # 'data' (default) | 'root'
    workdir: Optional[str] = None       # explicit path (optional)


def is_local_request(request: Request) -> bool:
    """Check if request is from localhost."""
    host = (request.client.host if request and request.client else None) or ""
    return host in {"127.0.0.1", "::1", "localhost"}


def require_shell_enabled_and_auth(request: Request, x_api_token: Optional[str] = None,
                                  shell_enabled: bool = False, shell_token: Optional[str] = None):
    """
    Validate shell API is enabled and request is authorized.
    
    Args:
        request: FastAPI request object
        x_api_token: API token from header
        shell_enabled: Whether shell API is enabled
        shell_token: Expected token value
    """
    if not shell_enabled:
        raise HTTPException(status_code=403, detail="Shell API is disabled. Set CEDARPY_SHELL_API_ENABLED=1 to enable.")
    
    # If a token is configured, require it
    if shell_token:
        # Allow header or cookie
        cookie_tok = request.cookies.get("Cedar-Shell-Token") if hasattr(request, "cookies") else None
        token = x_api_token or cookie_tok
        if token != shell_token:
            raise HTTPException(status_code=401, detail="Unauthorized (invalid or missing token)")
    else:
        # No token set: only allow local requests
        if not is_local_request(request):
            raise HTTPException(status_code=401, detail="Unauthorized (local requests only when no token configured)")


async def handle_shell_websocket(websocket: WebSocket, job_id: str, job_manager: ShellJobManager,
                                shell_enabled: bool = False, shell_token: Optional[str] = None):
    """
    Handle WebSocket connection for shell job streaming.
    
    Args:
        websocket: WebSocket connection
        job_id: Shell job ID
        job_manager: Shell job manager instance
        shell_enabled: Whether shell API is enabled
        shell_token: Expected token value
    """
    # Auth: token via query or cookie; else local-only when no token configured
    token_q = websocket.query_params.get("token") if hasattr(websocket, "query_params") else None
    
    if not shell_enabled:
        try:
            print(f"[ws] reject disabled job_id={job_id}")
        except Exception:
            pass
        await websocket.close(code=4403)
        return
    
    if shell_token:
        cookie_tok = websocket.cookies.get("Cedar-Shell-Token") if hasattr(websocket, "cookies") else None
        tok = token_q or cookie_tok
        if tok != shell_token:
            try:
                print(f"[ws] reject auth job_id={job_id}")
            except Exception:
                pass
            await websocket.close(code=4401)
            return
    else:
        # local-only
        try:
            client_host = (websocket.client.host if websocket.client else "")
        except Exception:
            client_host = ""
        if client_host not in {"127.0.0.1", "::1", "localhost"}:
            try:
                print(f"[ws] reject non-local job_id={job_id} from={client_host}")
            except Exception:
                pass
            await websocket.close(code=4401)
            return

    job = job_manager.get_job(job_id)
    if not job:
        try:
            print(f"[ws] reject not-found job_id={job_id}")
        except Exception:
            pass
        await websocket.close(code=4404)
        return

    try:
        ch = (websocket.client.host if websocket.client else "?")
        print(f"[ws] accept job_id={job_id} from={ch}")
    except Exception:
        pass
    await websocket.accept()
    
    # Send backlog
    try:
        for line in job.output_lines:
            await websocket.send_text(line)
    except Exception:
        # Ignore send errors on backlog
        pass

    # Live stream
    try:
        while True:
            try:
                line = job.queue.get(timeout=1.0)
            except Exception:
                if job.status in ("finished", "error", "killed"):
                    await websocket.send_text("__CEDARPY_EOF__")
                    break
                continue
            if line == "__CEDARPY_EOF__\n":
                await websocket.send_text("__CEDARPY_EOF__")
                break
            await websocket.send_text(line)
    except WebSocketDisconnect:
        # Client disconnected; nothing else to do
        try:
            print(f"[ws] disconnect job_id={job_id}")
        except Exception:
            pass
    except Exception as e:
        try:
            print(f"[ws] error job_id={job_id} err={type(e).__name__}: {e}")
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        try:
            print(f"[ws] closed job_id={job_id} status={job.status}")
        except Exception:
            pass


async def handle_health_websocket(websocket: WebSocket, shell_enabled: bool = False, 
                                 shell_token: Optional[str] = None):
    """
    Handle WebSocket health check endpoint.
    
    Args:
        websocket: WebSocket connection
        shell_enabled: Whether shell API is enabled
        shell_token: Expected token value
    """
    token_q = websocket.query_params.get("token") if hasattr(websocket, "query_params") else None
    
    if not shell_enabled:
        try:
            print("[ws-health] reject disabled")
        except Exception:
            pass
        await websocket.close(code=4403)
        return
    
    if shell_token:
        cookie_tok = websocket.cookies.get("Cedar-Shell-Token") if hasattr(websocket, "cookies") else None
        tok = token_q or cookie_tok
        if tok != shell_token:
            try:
                print("[ws-health] reject auth")
            except Exception:
                pass
            await websocket.close(code=4401)
            return
    else:
        try:
            client_host = (websocket.client.host if websocket.client else "")
        except Exception:
            client_host = ""
        if client_host not in {"127.0.0.1", "::1", "localhost"}:
            try:
                print(f"[ws-health] reject non-local from={client_host}")
            except Exception:
                pass
            await websocket.close(code=4401)
            return
    
    try:
        ch = (websocket.client.host if websocket.client else "?")
        print(f"[ws-health] accept from={ch}")
    except Exception:
        pass
    
    await websocket.accept()
    await websocket.send_text("[health] ok")
    await websocket.close()
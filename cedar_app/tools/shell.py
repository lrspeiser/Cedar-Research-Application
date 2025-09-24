"""
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

class ShellJob:
    def __init__(self, script: str, shell_path: Optional[str] = None, trace_x: bool = False, workdir: Optional[str] = None):
        self.id = uuid.uuid4().hex
        self.script = script
        # Preserve requested shell_path if provided; resolution and fallbacks happen at run-time
        self.shell_path = shell_path or os.environ.get("SHELL")
        self.trace_x = bool(trace_x)
        self.workdir = workdir or SHELL_DEFAULT_WORKDIR
        self.start_time = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None
        self.status = "starting"  # starting|running|finished|error|killed
        self.return_code: Optional[int] = None
        self.proc: Optional[subprocess.Popen] = None
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.output_lines: List[str] = []
        self.log_path = os.path.join(LOGS_DIR, f"{self.start_time.strftime('%Y%m%dT%H%M%SZ')}__{self.id}.log")
        self._lock = threading.Lock()

    def append_line(self, line: str):
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


# Shell job management
_shell_jobs: Dict[str, Any] = {}
_shell_jobs_lock = threading.Lock()

def _run_job(job: ShellJob):
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


def start_shell_job(script: str, shell_path: Optional[str] = None, trace_x: bool = False, workdir: Optional[str] = None) -> ShellJob:
    job = ShellJob(script=script, shell_path=shell_path, trace_x=trace_x, workdir=workdir)
    with _shell_jobs_lock:
        _shell_jobs[job.id] = job
    t = threading.Thread(target=_run_job, args=(job,), daemon=True)
    t.start()
    return job


def get_shell_job(job_id: str) -> Optional[ShellJob]:
    with _shell_jobs_lock:
        return _shell_jobs.get(job_id)

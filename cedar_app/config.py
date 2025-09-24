"""
Configuration module for Cedar app.
Handles environment variables, paths, and application settings.
"""

import os
import sys
from typing import Optional, List, Dict


def _load_dotenv_files(paths: List[str]) -> None:
    """
    Lightweight .env loader (no external deps). This is intentionally minimal and does not print values.
    It loads KEY=VALUE pairs, ignoring lines starting with # and blank lines. Quotes around values are trimmed.
    See README for more details about secret handling.
    """
    def _parse_line(line: str) -> Optional[tuple]:
        s = line.strip()
        if not s or s.startswith('#'):
            return None
        if '=' not in s:
            return None
        k, v = s.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if not k:
            return None
        return (k, v)
    
    for p in paths:
        try:
            if not p or not os.path.isfile(p):
                continue
            with open(p, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    kv = _parse_line(line)
                    if not kv:
                        continue
                    k, v = kv
                    # Do not override if already set in the environment
                    if os.getenv(k) is None:
                        os.environ[k] = v
        except Exception:
            # Best-effort; ignore parse errors
            pass


def _parse_env_file(path: str) -> Dict[str, str]:
    """Helper to parse a simple KEY=VALUE .env file."""
    out: Dict[str, str] = {}
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith('#') or '=' not in s:
                    continue
                k, v = s.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k:
                    out[k] = v
    except Exception:
        pass
    return out


def _initialize_environment():
    """Initialize environment from .env files."""
    # First pass: load from current working directory (.env) so early config can pick it up
    try:
        _load_dotenv_files([os.path.join(os.getcwd(), '.env')])
    except Exception:
        pass
    
    # Second pass: load .env from DATA_DIR and from app Resources (for packaged app)
    try:
        candidates: List[str] = [os.path.join(DATA_DIR, '.env')]
        # If running from an app bundle or PyInstaller, try Resources or _MEIPASS
        res_env_path = None
        try:
            if getattr(sys, 'frozen', False):
                app_dir = os.path.dirname(sys.executable)
                res_dir = os.path.abspath(os.path.join(app_dir, '..', 'Resources'))
                res_env_path = os.path.join(res_dir, '.env')
                candidates.append(res_env_path)
            else:
                # PyInstaller one-file (_MEIPASS)
                meipass = getattr(sys, '_MEIPASS', None)
                if meipass:
                    res_env_path = os.path.join(meipass, '.env')
                    candidates.append(res_env_path)
        except Exception:
            res_env_path = None
            pass
        
        # FIRST: if DATA_DIR/.env is missing, or present but missing keys found in Resources/.env, seed/merge into user data .env
        try:
            data_env = os.path.join(DATA_DIR, '.env')
            if res_env_path and os.path.isfile(res_env_path):
                os.makedirs(DATA_DIR, exist_ok=True)
                data_vals = _parse_env_file(data_env) if os.path.isfile(data_env) else {}
                res_vals = _parse_env_file(res_env_path)
                
                # Add this print statement for debugging:
                try:
                    print(f"[DEBUG] Seeding check. Bundled keys: {list(res_vals.keys())}, User keys: {list(data_vals.keys())}")
                except Exception:
                    pass
                
                to_merge: Dict[str, str] = {}
                for key_name in ("OPENAI_API_KEY", "CEDARPY_OPENAI_API_KEY"):
                    if key_name in res_vals and key_name not in data_vals:
                        to_merge[key_name] = res_vals[key_name]
                
                # Add this print statement for debugging:
                try:
                    print(f"[DEBUG] Keys to merge into user .env: {list(to_merge.keys())}")
                except Exception:
                    pass
                
                if (not os.path.isfile(data_env)) or to_merge:
                    try:
                        with open(data_env, 'a', encoding='utf-8', errors='ignore') as f:
                            for k, v in to_merge.items():
                                f.write(f"{k}={v}\n")
                        try:
                            print(f"[DEBUG] Successfully wrote keys to {data_env}")
                        except Exception:
                            pass
                    except Exception as e:
                        # Replace 'pass' with actual error logging
                        try:
                            print(f"[ERROR] Failed to write to user .env file at {data_env}: {e}")
                        except Exception:
                            pass
        except Exception:
            pass
        
        # THEN: load .env files (DATA_DIR takes precedence by being first)
        _load_dotenv_files(candidates)
    except Exception:
        pass


# Core paths configuration
# Prefer a generic CEDARPY_DATABASE_URL for the central registry only; otherwise use SQLite in ~/CedarPyData/cedarpy.db
# See PROJECT_SEPARATION_README.md for architecture details.
HOME_DIR = os.path.expanduser("~")
DATA_DIR = os.getenv("CEDARPY_DATA_DIR", os.path.join(HOME_DIR, "CedarPyData"))
DEFAULT_SQLITE_PATH = os.path.join(DATA_DIR, "cedarpy.db")
PROJECTS_ROOT = os.path.join(DATA_DIR, "projects")

# Central registry DB (projects list only)
REGISTRY_DATABASE_URL = os.getenv("CEDARPY_DATABASE_URL") or f"sqlite:///{DEFAULT_SQLITE_PATH}"

# Deprecated: CEDARPY_UPLOAD_DIR (files now under per-project folders). Keep for backward compatibility during migration.
# Default the legacy uploads path under the user data dir so it is writable when running from a read-only app bundle.
# See PROJECT_SEPARATION_README.md for details.
_default_legacy_dir = os.path.join(DATA_DIR, "user_uploads")
LEGACY_UPLOAD_DIR = os.getenv("CEDARPY_UPLOAD_DIR", _default_legacy_dir)

# Shell API feature flag and token
# See README for details on enabling and securing the Shell API.
# - CEDARPY_SHELL_API_ENABLED: "1" to enable the UI and API, default "0" (disabled)
# - CEDARPY_SHELL_API_TOKEN: optional token. If set, requests must include X-API-Token header matching this value.
#   If unset, API is limited to local requests (127.0.0.1/::1) only.
# Default: ENABLED (set to "0" to disable). We default-on to match DMG behavior and ease local development.
SHELL_API_ENABLED = str(os.getenv("CEDARPY_SHELL_API_ENABLED", "1")).strip().lower() not in {"", "0", "false", "no", "off"}
SHELL_API_TOKEN = os.getenv("CEDARPY_SHELL_API_TOKEN")

# Logs directory for shell runs (outside DMG and writable)
LOGS_DIR = os.path.join(DATA_DIR, "logs", "shell")

# Default working directory for shell jobs (scoped, safe by default)
SHELL_DEFAULT_WORKDIR = os.getenv("CEDARPY_SHELL_WORKDIR") or DATA_DIR

# Auto-start chat on upload (client uses this to initiate WS after redirect)
# See README: "Auto-start chat on upload" for configuration and behavior.
UPLOAD_AUTOCHAT_ENABLED = str(os.getenv("CEDARPY_UPLOAD_AUTOCHAT", "1")).strip().lower() not in {"", "0", "false", "no", "off"}

# Initialize directories
def initialize_directories():
    """Ensure all required directories exist."""
    # Ensure writable dirs exist (important when running from a read-only DMG)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PROJECTS_ROOT, exist_ok=True)
    os.makedirs(os.path.dirname(DEFAULT_SQLITE_PATH), exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    try:
        os.makedirs(SHELL_DEFAULT_WORKDIR, exist_ok=True)
    except Exception:
        pass


# Initialize environment on module import
_initialize_environment()
initialize_directories()
"""
API Routes for Cedar
=====================

This module contains all API route handlers including:
- Settings management routes
- Model change endpoints
- Client logging endpoints
- File serving endpoints
"""

import os
import html
from typing import Optional, Dict, Any
from fastapi import Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles


def settings_page(msg: Optional[str] = None, env_get_fn=None, llm_reach_ok_fn=None, 
                  llm_reach_reason_fn=None, layout_fn=None, data_dir=None, 
                  llm_client_config_fn=None):
    """
    Render the settings page.
    
    Args:
        msg: Optional message to display
        env_get_fn: Function to get environment variables
        llm_reach_ok_fn: Function to check LLM reachability
        llm_reach_reason_fn: Function to get LLM reachability reason
        layout_fn: Layout function for HTML rendering
        data_dir: Data directory path
        llm_client_config_fn: Function to get LLM client config
    """
    # Do not display the actual key; show presence only
    key_present = bool(env_get_fn("CEDARPY_OPENAI_API_KEY") or env_get_fn("OPENAI_API_KEY"))
    model = env_get_fn("CEDARPY_OPENAI_MODEL") or env_get_fn("OPENAI_API_KEY_MODEL") or env_get_fn("CEDARPY_OPENAI_MODEL") or "gpt-5"
    banner = f"<div class='notice'>{html.escape(msg)}</div>" if msg else ""
    settings_path = os.path.join(data_dir, '.env')
    
    body = f"""
    <h1>Settings</h1>
    {banner}
    <p class='muted'>LLM keys are read from <code>{html.escape(settings_path)}</code>. We will not display keys here.</p>
    <p>OpenAI key status: <strong>{'Present' if key_present else 'Missing'}</strong></p>
    <p>LLM connectivity: {('✅ <strong>OK</strong> – ' + html.escape(str(model))) if llm_reach_ok_fn() else ('❌ <strong>Unavailable</strong> – ' + html.escape(llm_reach_reason_fn()))}</p>
    <form method='post' action='/settings/save'>
      <div>
        <label>OpenAI API Key</label><br/>
        <input type='password' name='openai_key' placeholder='sk-...' style='width:420px' autocomplete='off' />
      </div>
      <div style='margin-top:8px;'>
        <label>Model (optional)</label><br/>
        <input type='text' name='model' value='{html.escape(str(model))}' style='width:420px' />
      </div>
      <div style='margin-top:12px;'>
        <button type='submit'>Save</button>
      </div>
    </form>
    """
    return layout_fn("Settings", body, llm_client_config_fn=llm_client_config_fn)


def settings_save(openai_key: str = Form(""), model: str = Form(""), env_set_many_fn=None):
    """
    Save settings to environment file.
    
    Args:
        openai_key: OpenAI API key
        model: Model name
        env_set_many_fn: Function to set multiple environment variables
    """
    # Persist to ~/CedarPyData/.env; do not print the key
    updates: Dict[str, str] = {}
    if openai_key and str(openai_key).strip():
        updates["OPENAI_API_KEY"] = str(openai_key).strip()
    if model and str(model).strip():
        updates["CEDARPY_OPENAI_MODEL"] = str(model).strip()
    if updates:
        env_set_many_fn(updates)
        return RedirectResponse("/settings?msg=Saved", status_code=303)
    else:
        return RedirectResponse("/settings?msg=No+changes", status_code=303)


def api_model_change(payload: Dict[str, Any], env_set_many_fn=None):
    """
    API endpoint to change the LLM model from the dropdown.
    
    Args:
        payload: Request payload containing model selection
        env_set_many_fn: Function to set multiple environment variables
    """
    try:
        model = str(payload.get("model", "")).strip()
        if not model:
            return JSONResponse({"ok": False, "error": "No model specified"}, status_code=400)
        
        # Validate model is one of the allowed ones
        allowed_models = {"gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4o"}
        if model not in allowed_models:
            return JSONResponse({"ok": False, "error": f"Invalid model: {model}"}, status_code=400)
        
        # Update the model in environment and settings file
        updates = {"CEDARPY_OPENAI_MODEL": model}
        env_set_many_fn(updates)
        
        # Log the change
        try:
            print(f"[model-change] Changed LLM model to {model}")
        except Exception:
            pass
        
        return JSONResponse({"ok": True, "model": model})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


def api_chat_ack(payload: Dict[str, Any], ack_store: Dict):
    """
    WebSocket acknowledgment endpoint.
    
    Args:
        payload: Request payload containing event ID
        ack_store: Store for acknowledgment records
    """
    from datetime import datetime
    
    eid = str((payload or {}).get('eid') or '').strip()
    if not eid:
        return JSONResponse({"ok": False, "error": "missing eid"}, status_code=400)
    rec = ack_store.get(eid)
    if rec:
        rec['acked'] = True
        rec['ack_at'] = datetime.utcnow().isoformat()+"Z"
        try:
            print(f"[ack] eid={eid} type={rec.get('info',{}).get('type')} thread={rec.get('info',{}).get('thread_id')}")
        except Exception:
            pass
        return JSONResponse({"ok": True})
    try:
        print(f"[ack-miss] unknown eid={eid} payload={payload}")
    except Exception:
        pass
    return JSONResponse({"ok": False, "error": "unknown eid"}, status_code=404)


def serve_project_upload(project_id: int, path: str, project_dirs_fn):
    """
    Serve uploaded files for a specific project.
    
    Args:
        project_id: Project ID
        path: File path within the project
        project_dirs_fn: Function to get project directories
    """
    base = project_dirs_fn(project_id)["files_root"]
    ab = os.path.abspath(os.path.join(base, path))
    base_ab = os.path.abspath(base)
    if not ab.startswith(base_ab) or not os.path.isfile(ab):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(ab)
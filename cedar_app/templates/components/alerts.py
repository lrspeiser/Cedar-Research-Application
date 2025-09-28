"""
Alert and message components for Cedar app
"""

from typing import Optional
from main_helpers import escape


def success_alert(message: str, dismissible: bool = True) -> str:
    """Generate a success alert HTML component."""
    dismiss_btn = """
        <button onclick="this.parentElement.style.display='none'" 
                style="background: transparent; border: none; color: white; cursor: pointer; font-size: 18px; padding: 0;">
            ✕
        </button>
    """ if dismissible else ""
    
    return f"""
        <div style="background-color: #10b981; color: white; padding: 12px; border-radius: 6px; 
                    margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between;">
            <span>{escape(message)}</span>
            {dismiss_btn}
        </div>
    """


def error_alert(message: str, dismissible: bool = True) -> str:
    """Generate an error alert HTML component."""
    dismiss_btn = """
        <button onclick="this.parentElement.style.display='none'" 
                style="background: transparent; border: none; color: white; cursor: pointer; font-size: 18px; padding: 0;">
            ✕
        </button>
    """ if dismissible else ""
    
    return f"""
        <div style="background-color: #ef4444; color: white; padding: 12px; border-radius: 6px; 
                    margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between;">
            <span>{escape(message)}</span>
            {dismiss_btn}
        </div>
    """


def info_alert(message: str, dismissible: bool = True) -> str:
    """Generate an info alert HTML component."""
    dismiss_btn = """
        <button onclick="this.parentElement.style.display='none'" 
                style="background: transparent; border: none; color: white; cursor: pointer; font-size: 18px; padding: 0;">
            ✕
        </button>
    """ if dismissible else ""
    
    return f"""
        <div style="background-color: #3b82f6; color: white; padding: 12px; border-radius: 6px; 
                    margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between;">
            <span>{escape(message)}</span>
            {dismiss_btn}
        </div>
    """


def message_alert(message: Optional[str]) -> str:
    """Generate an alert based on message content."""
    if not message:
        return ""
    
    # Auto-detect message type based on content
    message_lower = message.lower()
    if "successfully" in message_lower or "deleted" in message_lower or "created" in message_lower:
        return success_alert(message)
    elif "error" in message_lower or "failed" in message_lower:
        return error_alert(message)
    else:
        return info_alert(message)
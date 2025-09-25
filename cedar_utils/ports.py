"""
cedar_utils/ports.py

Unified port selection helpers for CedarPy.
Provides a single source of truth for finding available ports.
"""

import socket
from typing import Optional


def choose_listen_port(host: str, desired: int) -> int:
    """
    Choose an available port for listening.
    
    Args:
        host: The host address to bind to (e.g., "127.0.0.1")
        desired: The desired port number
    
    Returns:
        The desired port if available, otherwise a random available port
    """
    try:
        # Try the desired port first
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, desired))
            s.close()
            return desired
        except Exception:
            try:
                s.close()
            except Exception:
                pass
        
        # If desired port is not available, find a free port
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s2.bind((host, 0))  # Bind to port 0 to get a random available port
        port = s2.getsockname()[1]
        s2.close()
        return int(port)
    except Exception:
        # If all else fails, return the desired port
        return desired


def is_port_available(host: str, port: int) -> bool:
    """
    Check if a port is available for binding.
    
    Args:
        host: The host address to check
        port: The port number to check
    
    Returns:
        True if the port is available, False otherwise
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
            s.close()
            return True
        except Exception:
            return False
        finally:
            try:
                s.close()
            except Exception:
                pass
    except Exception:
        return False


# Backward compatibility aliases
_choose_listen_port = choose_listen_port
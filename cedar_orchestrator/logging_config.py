"""
Centralized Logging Configuration for CedarPy Backend

This module provides comprehensive file-based logging for all backend components.
Every backend function should use this logging system to provide detailed execution traces.

See: docs/LOGGING_SYSTEM.md for usage documentation
"""

import logging
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

# Log directory
LOG_DIR = Path(os.path.expanduser("~/Library/Logs/CedarPy"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Log format - very detailed
DETAILED_FORMAT = (
    '%(asctime)s.%(msecs)03d | '
    '%(levelname)-8s | '
    '%(name)-40s | '
    '%(funcName)-25s | '
    'Line %(lineno)-4d | '
    '%(message)s'
)

DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


class CedarLogger:
    """
    Centralized logger factory for CedarPy backend.
    
    Creates loggers with both file and console output, configured with
    detailed formatting for debugging.
    
    Usage:
        from cedar_orchestrator.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Step completed successfully")
    """
    
    _loggers = {}
    _main_log_file = None
    _session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    @classmethod
    def get_main_log_file(cls) -> Path:
        """Get the main log file path for this session"""
        if cls._main_log_file is None:
            cls._main_log_file = LOG_DIR / f"backend_{cls._session_timestamp}.log"
        return cls._main_log_file
    
    @classmethod
    def get_logger(
        cls,
        name: str,
        level: int = logging.DEBUG,
        also_to_console: bool = True
    ) -> logging.Logger:
        """
        Get or create a logger with file and optional console output.
        
        All loggers write to the same main log file for this session,
        plus component-specific log files.
        
        Args:
            name: Logger name (usually __name__)
            level: Log level (default DEBUG for maximum detail)
            also_to_console: Whether to also log to console/stdout
            
        Returns:
            Configured logger instance
        """
        
        # Return existing logger if already configured
        if name in cls._loggers:
            return cls._loggers[name]
        
        # Create new logger
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False  # Don't propagate to root logger
        
        # Clear any existing handlers
        logger.handlers.clear()
        
        # Create formatter
        formatter = logging.Formatter(DETAILED_FORMAT, datefmt=DATE_FORMAT)
        
        # 1. Main log file handler (all backend logs go here)
        main_log_file = cls.get_main_log_file()
        main_handler = logging.FileHandler(main_log_file, encoding='utf-8')
        main_handler.setLevel(logging.DEBUG)
        main_handler.setFormatter(formatter)
        logger.addHandler(main_handler)
        
        # 2. Component-specific log file (for this module only)
        # Extract component name from logger name
        component_name = name.split('.')[-1] if '.' in name else name
        component_log_file = LOG_DIR / f"{component_name}_{cls._session_timestamp}.log"
        component_handler = logging.FileHandler(component_log_file, encoding='utf-8')
        component_handler.setLevel(logging.DEBUG)
        component_handler.setFormatter(formatter)
        logger.addHandler(component_handler)
        
        # 3. Console handler (optional)
        if also_to_console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)  # Less verbose for console
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # Cache logger
        cls._loggers[name] = logger
        
        # Log logger creation
        logger.debug(f"Logger '{name}' initialized")
        logger.debug(f"  Main log: {main_log_file}")
        logger.debug(f"  Component log: {component_log_file}")
        logger.debug(f"  Console: {also_to_console}")
        
        return logger
    
    @classmethod
    def log_function_entry(cls, logger: logging.Logger, func_name: str, **kwargs):
        """
        Log entry into a function with parameters.
        
        Usage:
            logger = get_logger(__name__)
            log_function_entry(logger, "my_function", param1=value1, param2=value2)
        """
        logger.info(f"→ ENTERING {func_name}")
        if kwargs:
            for key, value in kwargs.items():
                # Truncate long values
                str_value = str(value)
                if len(str_value) > 100:
                    str_value = str_value[:100] + "..."
                logger.debug(f"  {key} = {str_value}")
    
    @classmethod
    def log_function_exit(cls, logger: logging.Logger, func_name: str, result=None):
        """
        Log exit from a function with optional result.
        
        Usage:
            logger = get_logger(__name__)
            log_function_exit(logger, "my_function", result=return_value)
        """
        logger.info(f"← EXITING {func_name}")
        if result is not None:
            str_result = str(result)
            if len(str_result) > 100:
                str_result = str_result[:100] + "..."
            logger.debug(f"  result = {str_result}")
    
    @classmethod
    def log_step(cls, logger: logging.Logger, step: str, details: Optional[str] = None):
        """
        Log a step in a process.
        
        Usage:
            logger = get_logger(__name__)
            log_step(logger, "Connecting to database", "host=localhost")
        """
        logger.info(f"  ▸ {step}")
        if details:
            logger.debug(f"    {details}")
    
    @classmethod
    def log_success(cls, logger: logging.Logger, message: str, details: Optional[str] = None):
        """Log a successful operation"""
        logger.info(f"✓ SUCCESS: {message}")
        if details:
            logger.debug(f"    {details}")
    
    @classmethod
    def log_error(cls, logger: logging.Logger, message: str, exception: Optional[Exception] = None):
        """Log an error"""
        logger.error(f"✗ ERROR: {message}")
        if exception:
            logger.error(f"    {type(exception).__name__}: {exception}")
            logger.debug("Stack trace:", exc_info=True)
    
    @classmethod
    def log_warning(cls, logger: logging.Logger, message: str, details: Optional[str] = None):
        """Log a warning"""
        logger.warning(f"⚠ WARNING: {message}")
        if details:
            logger.debug(f"    {details}")
    
    @classmethod
    def get_session_info(cls) -> dict:
        """Get information about current logging session"""
        return {
            "session_timestamp": cls._session_timestamp,
            "main_log_file": str(cls.get_main_log_file()),
            "log_directory": str(LOG_DIR),
            "active_loggers": list(cls._loggers.keys())
        }


# Convenience functions for direct import
def get_logger(name: str, level: int = logging.DEBUG, also_to_console: bool = True) -> logging.Logger:
    """Get or create a logger - convenience wrapper"""
    return CedarLogger.get_logger(name, level, also_to_console)


def log_function_entry(logger: logging.Logger, func_name: str, **kwargs):
    """Log function entry - convenience wrapper"""
    CedarLogger.log_function_entry(logger, func_name, **kwargs)


def log_function_exit(logger: logging.Logger, func_name: str, result=None):
    """Log function exit - convenience wrapper"""
    CedarLogger.log_function_exit(logger, func_name, result)


def log_step(logger: logging.Logger, step: str, details: Optional[str] = None):
    """Log a step - convenience wrapper"""
    CedarLogger.log_step(logger, step, details)


def log_success(logger: logging.Logger, message: str, details: Optional[str] = None):
    """Log success - convenience wrapper"""
    CedarLogger.log_success(logger, message, details)


def log_error(logger: logging.Logger, message: str, exception: Optional[Exception] = None):
    """Log error - convenience wrapper"""
    CedarLogger.log_error(logger, message, exception)


def log_warning(logger: logging.Logger, message: str, details: Optional[str] = None):
    """Log warning - convenience wrapper"""
    CedarLogger.log_warning(logger, message, details)


# Print session info on module import
if __name__ != "__main__":
    session_info = CedarLogger.get_session_info()
    print(f"[CedarLogger] Logging session started: {session_info['session_timestamp']}")
    print(f"[CedarLogger] Main log file: {session_info['main_log_file']}")

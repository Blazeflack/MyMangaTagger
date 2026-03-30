# services/logger.py

"""
Module for logging within MyMangaTagger, providing both rotating file and console handlers,
an in-memory log store, and alert callbacks for warnings and errors.
"""
import logging
import traceback
import threading
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, List, Optional, Tuple

DEFAULT_LOG_PATH = Path(__file__).parent.parent / "mymangatagger.log"

# In-memory log store with a maximum size to avoid unbounded growth
decor = deque(maxlen=1000)
_store_lock = threading.Lock()
_log_alert_callback = None  # type: Optional[Callable[[str], None]]

# Configure the main logger
_logger = logging.getLogger("mymangatagger")
_logger.setLevel(logging.DEBUG)

# File handler with rotation
_file_handler = RotatingFileHandler(
    filename=str(DEFAULT_LOG_PATH),
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=3,
    encoding="utf-8",
)
_formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
_file_handler.setFormatter(_formatter)
_logger.addHandler(_file_handler)

# Console output handler
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)
_logger.addHandler(_console_handler)

_logger.propagate = False

LEVEL_NAMES = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}

def log(level: str, message: str, *, exc_info: bool = False) -> None:
    """
    Log a message to file, console, and in-memory store; send alerts for WARN+ levels.

    Args:
        level (str): Log level name (e.g., "DEBUG", "INFO", "WARN", "ERROR").
        message (str): The message to log.
        exc_info (bool, optional): If True, append current stack trace. Defaults to False.
    """
    lvl = level.upper()
    numeric = getattr(logging, lvl, logging.INFO)

    if exc_info:
        # Append traceback to message
        message = f"{message}\n{traceback.format_exc()}"

    _logger.log(numeric, message, exc_info=exc_info)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry: Tuple[str, str, str] = (timestamp, lvl, message)
    with _store_lock:
        decor.append(entry)

    # Trigger alert callback on warnings or errors
    if _log_alert_callback and lvl in {"WARN", "WARNING", "ERROR", "CRITICAL"}:
        _log_alert_callback(lvl)

def get_logs(min_level: str = "DEBUG") -> List[Tuple[str, str, str]]:
    """
    Retrieve in-memory log entries at or above a specified level.

    Args:
        min_level (str, optional): Lower bound for log levels (e.g., "INFO"). Defaults to "DEBUG".

    Returns:
        List[Tuple[str, str, str]]: List of (timestamp, level, message) entries.
    """
    min_lvl_numeric = getattr(logging, min_level.upper(), logging.DEBUG)
    with _store_lock:
        return [entry for entry in decor if getattr(logging, entry[1], logging.DEBUG) >= min_lvl_numeric]

def clear_logs() -> None:
    """
    Clear all entries from the in-memory log store.
    """
    with _store_lock:
        decor.clear()

def set_log_alert_callback(callback: Optional[Callable[[str], None]]) -> None:
    """
    Register or deregister a callback for warning/error alerts.

    Args:
        callback (Optional[Callable[[str], None]]): Function that accepts a log level string.
            Pass None to disable alerts.
    """
    global _log_alert_callback
    _log_alert_callback = callback

def set_level(level_str: str) -> None:
    """
    Set the global logger level by name.

    Args:
        level_str (str): One of "DEBUG", "INFO", "WARN", etc.
    """
    numeric = getattr(logging, level_str.upper(), logging.INFO)
    _logger.setLevel(numeric)

def set_debug(enabled: bool) -> None:
    """
    Convenience function to toggle debug logging.

    Args:
        enabled (bool): If True, set level to DEBUG; otherwise set to WARN.
    """
    _logger.setLevel(logging.DEBUG if enabled else logging.WARN)

# Expose module-level logger for direct use
logger = _logger

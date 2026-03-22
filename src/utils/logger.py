"""
Logging Configuration Module
Provides consistent logging throughout the application
"""

import os
import sys
from pathlib import Path

from loguru import logger

# Create log directory
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Get log level and retention period from environment variables
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_RETENTION = os.getenv("LOG_RETENTION", "7 days")

# Configure logger only once to avoid duplicate output when module is reloaded or imported from multiple paths
_CONFIGURED = False


def _configure_logger() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logger.remove()  # Remove default handler (and any existing)

    # Log to standard error (catch=True avoids BrokenPipeError when stderr pipe is closed, e.g. in Docker)
    logger.add(
        sys.stderr,
        level=LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        catch=True,
    )

    _file_fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    for path, level in ((log_dir / "app.log", LOG_LEVEL), (log_dir / "error.log", "ERROR")):
        try:
            logger.add(
                path,
                rotation="1 day",
                retention=LOG_RETENTION,
                level=level,
                format=_file_fmt,
                encoding="utf-8",
            )
        except OSError:
            # e.g. logs/ owned by root or read-only filesystem — stderr logging still works
            pass

    _CONFIGURED = True


_configure_logger()


def get_logger(name):
    """
    Get a named logger

    Args:
        name (str): Logger name (usually the module name)

    Returns:
        loguru.Logger: Configured logger instance
    """
    return logger.bind(name=name)

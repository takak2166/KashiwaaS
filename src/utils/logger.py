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

# Configure logger
logger.remove()  # Remove default handler

# Log to standard error
logger.add(
    sys.stderr,
    level=LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)

# Log to file
logger.add(
    log_dir / "app.log",
    rotation="1 day",
    retention=LOG_RETENTION,
    level=LOG_LEVEL,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    encoding="utf-8",
)

# Log errors to a separate file
logger.add(
    log_dir / "error.log",
    rotation="1 day",
    retention=LOG_RETENTION,
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    encoding="utf-8",
)


def get_logger(name):
    """
    Get a named logger

    Args:
        name (str): Logger name (usually the module name)

    Returns:
        loguru.Logger: Configured logger instance
    """
    return logger.bind(name=name)
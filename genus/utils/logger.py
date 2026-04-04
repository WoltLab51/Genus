"""
Logging Utilities

Provides centralized logging configuration and utilities.
"""

import logging
import sys
from typing import Optional
from genus.config import Config


def setup_logging(level: Optional[str] = None, log_file: Optional[str] = None) -> None:
    """
    Set up logging configuration for the entire system.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs to
    """
    config = Config()

    log_level = level or config.get("logging.level", "INFO")
    log_format = config.get("logging.format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    log_file = log_file or config.get("logging.file")

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        handlers=_get_handlers(log_file),
    )


def _get_handlers(log_file: Optional[str] = None) -> list:
    """
    Get logging handlers.

    Args:
        log_file: Optional file path for file handler

    Returns:
        List of logging handlers
    """
    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        handlers.append(logging.FileHandler(log_file))

    return handlers


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Name of the logger (typically __name__ of the module)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)

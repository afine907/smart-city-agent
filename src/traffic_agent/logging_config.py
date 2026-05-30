"""
Logging Configuration — Structured logging setup for the traffic agent.

Provides consistent logging configuration across all modules.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from typing import Any


def setup_logging(
    level: str = "INFO",
    format_type: str = "structured",
    log_file: str | None = None,
) -> None:
    """
    Configure logging for the traffic agent.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: "structured" for JSON-like, "simple" for human-readable
        log_file: Optional file path for log output
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    if format_type == "structured":
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    handlers: list[logging.Handler] = [console_handler]

    # File handler if specified (with rotation to prevent unbounded growth)
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        force=True,
    )

    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


class StructuredFormatter(logging.Formatter):
    """JSON-like structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured text."""
        parts = [
            f"timestamp={self.formatTime(record, '%Y-%m-%dT%H:%M:%S')}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"message={record.getMessage()}",
        ]

        # Add extra fields
        if hasattr(record, "extra_fields"):
            for key, value in record.extra_fields.items():
                parts.append(f"{key}={value}")

        # Add exception info
        if record.exc_info and record.exc_info[0] is not None:
            parts.append(f"exception={self.formatException(record.exc_info)}")

        return " | ".join(parts)


def get_logger(name: str, **extra: Any) -> logging.LoggerAdapter:
    """
    Get a logger with extra context fields.

    Args:
        name: Logger name (usually __name__)
        **extra: Extra fields to include in all log messages

    Returns:
        LoggerAdapter with extra context
    """
    logger = logging.getLogger(name)
    return logging.LoggerAdapter(logger, {"extra_fields": extra})

import logging
import sys
from pathlib import Path

from pythonjsonlogger import json as jsonlogger

ROOT = Path(__file__).parent.absolute()


class EmojiFormatter(logging.Formatter):
    """Custom formatter that adds emojis based on log level."""

    EMOJIS: dict[int, str] = {
        logging.DEBUG: "🐛",
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🚨",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Add emoji to the record"""
        record.emoji = self.EMOJIS.get(record.levelno, "")
        return super().format(record)


def create_logger(
    name: str = "logger",
    log_level: int = logging.INFO,
    log_file: str | None = None,
    structured: bool = False,
) -> logging.Logger:
    """
    Create a configured logger with structured JSON output.

    Parameters:
    -----------
    name : str, optional
        Name of the logger, by default 'logger'
    log_level : int, optional
        Logging level, by default logging.INFO
    log_file : str, optional
        Path to log file. If None, logs to console, by default None
    structured : bool, optional
        If True, outputs JSON-formatted logs. If False, uses plain text format, by default False

    Returns:
    --------
    logging.Logger
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Clear any existing handlers
    logger.handlers.clear()

    # Create formatter based on structured flag
    if structured:
        # JSON formatter for structured logging
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            # Include extra fields passed via logger.info(..., extra={...})
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger_name",
            },
        )
    else:
        # Plain text formatter with emojis
        formatter = EmojiFormatter(
            fmt="%(asctime)s - %(name)s - [%(levelname)s] %(emoji)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def add_file_handler(
    logger: logging.Logger, log_file: str | Path, structured: bool = False
) -> logging.FileHandler:
    """Dynamically adds a file handler using the standard app format.

    Parameters
    ----------
    logger : logging.Logger
        The logger instance to which the file handler will be added.
    log_file : str | Path
        The path to the log file.
    structured : bool, optional
        If True, outputs JSON-formatted logs. If False, uses plain text format, by default False

    Returns
    -------
    logging.FileHandler
        The added file handler instance.
    """
    if structured:
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            rename_fields={
                "asctime": "timestamp",
                "levelname": "level",
                "name": "logger_name",
            },
        )
    else:
        formatter = EmojiFormatter(
            fmt="%(asctime)s - %(name)s - [%(levelname)s] %(emoji)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return file_handler


__all__ = ["ROOT"]

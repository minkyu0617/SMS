import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional


_loggers: dict = {}


def get_logger(name: str, level: Optional[str] = None, log_file: Optional[str] = None) -> logging.Logger:
    """Return a named logger. Creates it on first call, returns cached instance thereafter."""
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)

    log_level = getattr(logging, (level or os.getenv("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    logger.setLevel(log_level)

    if not logger.handlers:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        resolved_file = log_file or os.getenv("LOG_FILE", "logs/trading.log")
        if resolved_file:
            os.makedirs(os.path.dirname(resolved_file), exist_ok=True)
            file_handler = RotatingFileHandler(
                resolved_file,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    _loggers[name] = logger
    return logger

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from .resource_paths import log_file_path


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("voice1c")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        log_file_path(),
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.info("logging initialized")
    return logger


def open_log_file() -> bool:
    path = log_file_path()
    path.touch(exist_ok=True)
    os.startfile(str(path))
    return True

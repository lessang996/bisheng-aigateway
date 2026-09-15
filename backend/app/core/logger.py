import json
import logging
import os
from logging.handlers import RotatingFileHandler

from app.core.config import get_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("user_id", "request_time", "input", "output_summary", "error", "cache_key"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    settings = get_settings()
    log_level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    formatter = JsonFormatter()
    log_path = os.path.abspath(settings.log_file or "logs/gateway.log")
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    console_handler = next(
        (handler for handler in root_logger.handlers if getattr(handler, "_gateway_console", False)),
        None,
    )
    if console_handler is None:
        console_handler = logging.StreamHandler()
        console_handler._gateway_console = True  # type: ignore[attr-defined]
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    console_handler.setLevel(log_level)
    file_handler = next(
        (
            handler
            for handler in root_logger.handlers
            if isinstance(handler, RotatingFileHandler)
            and os.path.abspath(handler.baseFilename) == log_path
        ),
        None,
    )
    if file_handler is None:
        file_handler = RotatingFileHandler(
            filename=log_path,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
            delay=True,
        )
        file_handler._gateway_file = True  # type: ignore[attr-defined]
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    file_handler.setLevel(log_level)
    logging.getLogger(__name__).info(
        "logging initialized level=%s file=%s",
        logging.getLevelName(log_level),
        log_path,
    )

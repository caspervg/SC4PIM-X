"""Application-wide logging configuration for SC4PIM.

Modules obtain a logger with the standard idiom::

    import logging
    logger = logging.getLogger(__name__)

which places them under the ``sc4pimx`` namespace. :func:`configure_logging`
(called once from ``main()``) attaches a rotating file handler writing to
``%APPDATA%/sc4pimx/sc4pimx.log`` and, when enabled, a stderr handler. Runtime
defaults come from the ``[Logging]`` table in ``config.toml``. The
``SC4PIM_LOG_LEVEL`` environment variable remains as an emergency override for
troubleshooting a broken config.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import tempfile
import threading
from pathlib import Path

from . import config
from .paths import ensure_user_data_dir

LOGGER_NAME = "sc4pimx"
LOG_FILENAME = "sc4pimx.log"

_DEFAULT_LEVEL = logging.INFO
_configured = False
_previous_excepthook = None
_previous_threading_excepthook = None


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalised = value.strip().lower()
        if normalised in {"1", "true", "yes", "on"}:
            return True
        if normalised in {"0", "false", "no", "off"}:
            return False
    return default


def _as_int(value, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default


def _as_level(value, default: int = _DEFAULT_LEVEL) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        raw = value.strip().upper()
        if raw.isdecimal():
            return int(raw)
        return logging.getLevelNamesMapping().get(raw, default)
    return default


def _load_config() -> tuple[dict, BaseException | None]:
    data = {
        "enabled": True,
        "level": _DEFAULT_LEVEL,
        "file": True,
        "console": True,
        "filename": LOG_FILENAME,
        "max_bytes": 2_000_000,
        "backup_count": 3,
    }
    config_error = None
    try:
        raw = config.load().get("Logging", {})
    except Exception as exc:
        raw = {}
        config_error = exc

    if isinstance(raw, dict):
        data["enabled"] = _as_bool(raw.get("Enabled"), data["enabled"])
        data["level"] = _as_level(raw.get("Level"), data["level"])
        data["file"] = _as_bool(raw.get("File"), data["file"])
        data["console"] = _as_bool(raw.get("Console"), data["console"])
        filename = str(raw.get("Filename", data["filename"])).strip()
        data["filename"] = filename or LOG_FILENAME
        data["max_bytes"] = _as_int(raw.get("MaxBytes"), data["max_bytes"], minimum=1)
        data["backup_count"] = _as_int(raw.get("BackupCount"), data["backup_count"])

    if "SC4PIM_LOG_LEVEL" in os.environ:
        data["level"] = _as_level(os.environ.get("SC4PIM_LOG_LEVEL"), data["level"])

    return data, config_error


def _exception_tuple(exc: BaseException):
    return (type(exc), exc, exc.__traceback__)


def _log_setup_warning(logger: logging.Logger, message: str, exc: BaseException) -> None:
    logger.warning(message, exc_info=_exception_tuple(exc))


def _add_rotating_file_handler(logger: logging.Logger, formatter: logging.Formatter, options: dict) -> Path:
    log_path = Path(options["filename"])
    if not log_path.is_absolute():
        log_path = ensure_user_data_dir() / log_path
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=options["max_bytes"],
        backupCount=options["backup_count"],
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return log_path


def install_excepthooks(logger: logging.Logger | None = None) -> None:
    """Route otherwise-unhandled exceptions through the application logger."""
    global _previous_excepthook, _previous_threading_excepthook

    logger = logger or logging.getLogger(LOGGER_NAME)
    if _previous_excepthook is None:
        _previous_excepthook = sys.excepthook

        def log_unhandled_exception(exc_type, exc, tb):
            if issubclass(exc_type, KeyboardInterrupt):
                _previous_excepthook(exc_type, exc, tb)
                return
            logger.critical("Unhandled exception", exc_info=(exc_type, exc, tb))

        sys.excepthook = log_unhandled_exception

    if _previous_threading_excepthook is None:
        _previous_threading_excepthook = threading.excepthook

        def log_thread_exception(args):
            if args.exc_type is SystemExit:
                return
            logger.critical(
                "Unhandled exception in thread %s",
                args.thread.name if args.thread else "<unknown>",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )

        threading.excepthook = log_thread_exception


def configure_logging(level: int | None = None) -> logging.Logger:
    """Configure the ``sc4pimx`` logger once. Safe to call repeatedly."""
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    if _configured:
        return logger

    options, config_error = _load_config()
    effective_level = level if level is not None else options["level"]

    logger.setLevel(effective_level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    setup_errors: list[BaseException] = []
    log_paths: list[Path] = []
    if options["enabled"] and options["file"]:
        try:
            log_paths.append(_add_rotating_file_handler(logger, formatter, options))
        except OSError as exc:
            setup_errors.append(exc)
            fallback = options.copy()
            fallback["filename"] = str(Path(tempfile.gettempdir()) / LOG_FILENAME)
            try:
                log_paths.append(_add_rotating_file_handler(logger, formatter, fallback))
            except OSError as fallback_exc:
                setup_errors.append(fallback_exc)

    # stderr is None in a windowed PyInstaller build.
    if options["enabled"] and options["console"] and sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    install_excepthooks(logger)
    _configured = True

    if config_error is not None:
        _log_setup_warning(logger, "Could not read logging config; using defaults", config_error)
    for error in setup_errors:
        _log_setup_warning(logger, "Could not open configured log file", error)
    logger.debug(
        "Logging configured level=%s file=%s console=%s handlers=%d",
        logging.getLevelName(effective_level),
        ", ".join(str(path) for path in log_paths) if log_paths else "disabled",
        options["enabled"] and options["console"] and sys.stderr is not None,
        len(logger.handlers),
    )

    return logger

"""Logging setup of the naneos package.

The package follows the library convention: every module logs to a logger
below "naneos" and the package itself installs only a NullHandler, so nothing
is printed unless the application configures logging. Two helpers make the
common cases one call: enable_console_logging() and enable_file_logging().
"""

import logging
from logging import CRITICAL as LEVEL_CRITICAL
from logging import DEBUG as LEVEL_DEBUG
from logging import ERROR as LEVEL_ERROR
from logging import INFO as LEVEL_INFO
from logging import WARNING as LEVEL_WARNING
from pathlib import Path

__all__ = [
    "get_naneos_logger",
    "enable_console_logging",
    "enable_file_logging",
    "set_naneos_logger_save_path",
    "LEVEL_DEBUG",
    "LEVEL_INFO",
    "LEVEL_WARNING",
    "LEVEL_ERROR",
    "LEVEL_CRITICAL",
]

ROOT_LOGGER_NAME = "naneos"
DEFAULT_LOG_FILE_NAME = "naneos-devices.log"

_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
_COLORS = {
    logging.DEBUG: "\x1b[38;20m",  # grey
    logging.INFO: "\x1b[32;20m",  # green
    logging.WARNING: "\x1b[33;20m",  # yellow
    logging.ERROR: "\x1b[31;20m",  # red
    logging.CRITICAL: "\x1b[31;1m",  # bold red
}
_RESET = "\x1b[0m"


class CustomFormatter(logging.Formatter):
    """The naneos log line, optionally coloured by level for terminals."""

    def __init__(self, terminal: bool = False, fmt: str | None = None) -> None:
        fmt = fmt or _FORMAT
        super().__init__(fmt=fmt)
        self._by_level: dict[int, logging.Formatter] = {}
        if terminal:
            self._by_level = {
                level: logging.Formatter(f"{color} {fmt} {_RESET}")
                for level, color in _COLORS.items()
            }

    def format(self, record: logging.LogRecord) -> str:
        formatter = self._by_level.get(record.levelno)
        if formatter is None:
            return super().format(record)
        return formatter.format(record)


class _NaneosConsoleHandler(logging.StreamHandler):
    """Marker subclass so enable_console_logging() can find its own handler."""


class _NaneosFileHandler(logging.FileHandler):
    """Marker subclass so enable_file_logging() can find its own handler."""


def get_naneos_logger(name: str, level: int | None = None) -> logging.Logger:
    """The logger for a naneos module. Handlers and levels are configured by
    the application (or the enable_* helpers), not by the module.

    Args:
        name: Usually __name__ of the calling module.
        level: Optional level for this one logger. Library modules leave it
            unset so that one setting on the "naneos" logger controls them all.
    """
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)
    return logger


def enable_console_logging(level: int = logging.INFO, colored: bool = True) -> logging.Logger:
    """Print naneos log messages of at least `level` to stderr.

    Calling it again replaces the previous console handler, so the output is
    never duplicated. Returns the "naneos" logger.
    """
    root = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(root.handlers):
        if isinstance(handler, _NaneosConsoleHandler):
            root.removeHandler(handler)

    handler = _NaneosConsoleHandler()
    handler.setLevel(level)
    handler.setFormatter(CustomFormatter(terminal=colored))
    root.addHandler(handler)
    _lower_level_to(root, level)
    return root


def enable_file_logging(path: str | Path, level: int = logging.INFO) -> logging.Logger:
    """Append naneos log messages of at least `level` to a file.

    `path` may be a directory, in which case naneos-devices.log is created in
    it. Calling it again replaces the previous file handler. Returns the
    "naneos" logger.
    """
    path = Path(path).resolve()
    if path.is_dir():
        path = path / DEFAULT_LOG_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(root.handlers):
        if isinstance(handler, _NaneosFileHandler):
            handler.close()
            root.removeHandler(handler)

    handler = _NaneosFileHandler(str(path))
    handler.setLevel(level)
    handler.setFormatter(CustomFormatter(terminal=False))
    root.addHandler(handler)
    _lower_level_to(root, level)
    return root


def set_naneos_logger_save_path(path: str | Path) -> None:
    """Deprecated alias of enable_file_logging(), kept for naneos-devices <= 1.1.x."""
    enable_file_logging(path)


def _lower_level_to(logger: logging.Logger, level: int) -> None:
    """Make sure records of `level` reach the handlers without raising a level
    the application already set lower."""
    if logger.level == logging.NOTSET or logger.level > level:
        logger.setLevel(level)


# Library convention: never print anything unless the application asks for it.
logging.getLogger(ROOT_LOGGER_NAME).addHandler(logging.NullHandler())

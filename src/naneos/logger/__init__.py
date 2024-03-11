from logging import CRITICAL as LEVEL_CRITICAL
from logging import DEBUG as LEVEL_DEBUG
from logging import ERROR as LEVEL_ERROR
from logging import INFO as LEVEL_INFO
from logging import WARNING as LEVEL_WARNING

from naneos.logger.custom_logger import get_naneos_logger, set_naneos_logger_save_path

__all__ = [
    "get_naneos_logger",
    "set_naneos_logger_save_path",
    "LEVEL_DEBUG",
    "LEVEL_INFO",
    "LEVEL_WARNING",
    "LEVEL_ERROR",
    "LEVEL_CRITICAL",
]

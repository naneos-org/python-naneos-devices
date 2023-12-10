from logging import CRITICAL as LEVEL_CRITICAL
from logging import DEBUG as LEVEL_DEBUG
from logging import ERROR as LEVEL_ERROR
from logging import INFO as LEVEL_INFO
from logging import WARNING as LEVEL_WARNING

from naneos.logger.custom_logger import get_naneos_logger

__all__ = [
    "get_naneos_logger",
    "LEVEL_DEBUG",
    "LEVEL_INFO",
    "LEVEL_WARNING",
    "LEVEL_ERROR",
    "LEVEL_CRITICAL",
]

import logging
from typing import Optional


class CustomFormatter(logging.Formatter):
    _grey = "\x1b[38;20m"
    _green = "\x1b[32;20m"
    _yellow = "\x1b[33;20m"
    _red = "\x1b[31;20m"
    _bold_red = "\x1b[31;1m"
    _reset = "\x1b[0m"
    _format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    _FORMATS_TERMINAL: tuple[tuple[int, str], ...] = (
        (logging.DEBUG, _grey + _format + _reset),
        (logging.INFO, _green + _format + _reset),
        (logging.WARNING, _yellow + _format + _reset),
        (logging.ERROR, _red + _format + _reset),
        (logging.CRITICAL, _bold_red + _format + _reset),
    )
    _FORMATS_SAVE: tuple[tuple[int, str], ...] = (
        (logging.DEBUG, _format),
        (logging.INFO, _format),
        (logging.WARNING, _format),
        (logging.ERROR, _format),
        (logging.CRITICAL, _format),
    )

    def __init__(self, terminal: bool = False, fmt: Optional[str] = None):
        self._FORMATS = self._FORMATS_TERMINAL if terminal else self._FORMATS_SAVE
        if fmt is None:
            fmt = self._format
        super().__init__(fmt=fmt)

    def format(self, record):
        log_fmt = next(
            (x[1] for x in self._FORMATS if x[0] == record.levelno),
            self._FORMATS[0][1],
        )

        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def get_naneos_logger(name: str, level: int = logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    formatter_file = CustomFormatter(terminal=False)
    file_handler = logging.FileHandler("naneos-devices.log")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter_file)

    formatter_stream = CustomFormatter(terminal=True)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter_stream)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)

    return logger


if __name__ == "__main__":
    logger = get_naneos_logger(__name__, logging.DEBUG)
    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")
    logger.critical("critical message")

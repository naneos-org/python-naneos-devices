import logging
from pathlib import Path
from typing import Optional, Union

NANEOS_LOGGER_PATH = "logs/naneos-devices.log"


class CustomFormatter(logging.Formatter):
    _grey = "\x1b[38;20m"
    _green = "\x1b[32;20m"
    _yellow = "\x1b[33;20m"
    _red = "\x1b[31;20m"
    _bold_red = "\x1b[31;1m"
    _reset = "\x1b[0m"
    _format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    _FORMATS_TERMINAL = (
        (logging.DEBUG, f"{_grey} {_format} {_reset}"),
        (logging.INFO, f"{_green} {_format} {_reset}"),
        (logging.WARNING, f"{_yellow} {_format} {_reset}"),
        (logging.ERROR, f"{_red} {_format} {_reset}"),
        (logging.CRITICAL, f"{_bold_red} {_format} {_reset}"),
    )
    _FORMATS_SAVE = (
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

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = next(
            (x[1] for x in self._FORMATS if x[0] == record.levelno),
            self._FORMATS[0][1],
        )

        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def set_naneos_logger_save_path(path: Union[str, Path]) -> None:
    global NANEOS_LOGGER_PATH

    if isinstance(path, str):
        path = Path(path).resolve()

    if path.is_dir():
        path = path / "naneos-devices.log"

    # create file if it does not exist
    if not path.exists():
        path.touch()

    NANEOS_LOGGER_PATH = str(path)


def get_naneos_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    global NANEOS_LOGGER_PATH

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # check if NANEOS_LOGGER_PATH exists
    if Path(NANEOS_LOGGER_PATH).exists():
        formatter_file = CustomFormatter(terminal=False)
        file_handler = logging.FileHandler(NANEOS_LOGGER_PATH)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter_file)
        logger.addHandler(file_handler)

    formatter_stream = CustomFormatter(terminal=True)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter_stream)
    stream_handler.terminator = "\r\n"

    logger.addHandler(stream_handler)

    return logger


if __name__ == "__main__":
    set_naneos_logger_save_path("logs/naneos-devices.log")
    logger = get_naneos_logger(__name__, logging.DEBUG)
    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")
    logger.critical("critical message")

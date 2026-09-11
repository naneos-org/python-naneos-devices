"""Hardware-free tests for the logging convention of the package."""

import logging

from naneos.logger import (
    LEVEL_DEBUG,
    LEVEL_WARNING,
    enable_console_logging,
    enable_file_logging,
    get_naneos_logger,
)
from naneos.logger.custom_logger import ROOT_LOGGER_NAME, _NaneosConsoleHandler, _NaneosFileHandler


def _console_handlers() -> list[logging.Handler]:
    root = logging.getLogger(ROOT_LOGGER_NAME)
    return [h for h in root.handlers if isinstance(h, _NaneosConsoleHandler)]


def test_package_installs_only_a_null_handler_and_modules_add_nothing() -> None:
    import naneos.manager  # noqa: F401  (imports every module logger)

    root = logging.getLogger(ROOT_LOGGER_NAME)
    assert any(isinstance(h, logging.NullHandler) for h in root.handlers)

    for name, logger in logging.Logger.manager.loggerDict.items():
        if name.startswith("naneos.") and isinstance(logger, logging.Logger):
            assert logger.handlers == [], name
            assert logger.level == logging.NOTSET, name


def test_get_naneos_logger_only_sets_a_level_when_asked() -> None:
    assert get_naneos_logger("naneos.test_a").level == logging.NOTSET
    assert get_naneos_logger("naneos.test_b", LEVEL_DEBUG).level == logging.DEBUG


def test_enable_console_logging_is_idempotent(capsys) -> None:
    enable_console_logging(LEVEL_WARNING, colored=False)
    enable_console_logging(LEVEL_WARNING, colored=False)
    assert len(_console_handlers()) == 1

    get_naneos_logger("naneos.test_console").warning("hello console")
    get_naneos_logger("naneos.test_console").debug("not shown")

    captured = capsys.readouterr().err
    assert captured.count("hello console") == 1
    assert "not shown" not in captured

    for handler in _console_handlers():
        logging.getLogger(ROOT_LOGGER_NAME).removeHandler(handler)


def test_enable_file_logging_writes_to_the_directory_or_file(tmp_path) -> None:
    enable_file_logging(tmp_path, LEVEL_WARNING)
    get_naneos_logger("naneos.test_file").warning("hello file")

    log_file = tmp_path / "naneos-devices.log"
    assert "hello file" in log_file.read_text()

    root = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(root.handlers):
        if isinstance(handler, _NaneosFileHandler):
            handler.close()
            root.removeHandler(handler)

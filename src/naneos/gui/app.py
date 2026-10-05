"""The `naneos-gui` command: a tray icon that runs the device manager.

    naneos-gui                       start the tray app (a second start does nothing)
    naneos-gui --quit                ask the running one to stop and wait for it
    naneos-gui --autostart on|off|status
    naneos-gui --integration install|remove   app bundle / application menu entry
    naneos-gui --version

Everything but the tray app itself works without Qt, so the installers can use
it right after installing and a missing `naneos-devices[gui]` gets a clear hint.
"""

import argparse
import logging
import signal
import sys
import threading
from types import TracebackType
from typing import Any

from naneos import __version__
from naneos.gui.integration import (
    current_platform,
    get_autostart,
    install_integration,
    log_dir,
    remove_integration,
)
from naneos.logger import (
    DEFAULT_LOG_FILE_NAME,
    enable_console_logging,
    enable_file_logging,
    get_naneos_logger,
)

logger = get_naneos_logger("naneos.gui.app")

LOG_MAX_BYTES = 5_000_000
LOG_BACKUP_COUNT = 5
MISSING_QT_HINT = (
    "The naneos tray app needs Qt. Install it with:  uv tool install 'naneos-devices[gui]'\n"
    "or use the installer, see https://naneos-org.github.io/python-naneos-devices/"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="naneos-gui",
        description="Tray icon that reads every Partector in reach and uploads its data.",
    )
    parser.add_argument("--version", action="version", version=f"naneos-gui {__version__}")
    parser.add_argument(
        "--quit", action="store_true", help="stop the running tray app and wait until it is gone"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="how long --quit waits (default: %(default)s)",
    )
    parser.add_argument(
        "--autostart",
        choices=["on", "off", "status"],
        help="start at login on/off; status exits 0 if on, 1 if off",
    )
    parser.add_argument(
        "--integration",
        choices=["install", "remove"],
        help="macOS: the app bundle; Linux: the application menu entry",
    )
    parser.add_argument(
        "--no-upload", action="store_true", help="do not upload (for testing, nothing is sent)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="verbosity of the log file (default: %(default)s)",
    )
    return parser.parse_args(argv)


def _run_setup_actions(args: argparse.Namespace) -> int | None:
    """--integration and --autostart. The exit code, or None if none was asked for."""
    result: int | None = None
    if args.integration == "install":
        for path in install_integration():
            print(f"Installed {path}")
        result = 0
    elif args.integration == "remove":
        remove_integration()
        result = 0

    if args.autostart is not None:
        autostart = get_autostart()
        if args.autostart == "on":
            autostart.enable()
            print("Start at login: on")
            result = 0
        elif args.autostart == "off":
            autostart.disable()
            print("Start at login: off")
            result = 0
        else:
            enabled = autostart.enabled()
            print(f"Start at login: {'on' if enabled else 'off'}")
            result = 0 if enabled else 1
    return result


def _quit_running(timeout: float) -> int:
    try:
        from naneos.gui.instance import quit_running
    except ImportError:
        return 0  # no Qt in this environment, so no tray app can be running from it
    return quit_running(timeout)


def _install_exception_logging() -> None:
    """Under pythonw there is no stderr, so an uncaught exception would vanish."""

    def log_uncaught(
        exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
    ) -> None:
        logger.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def log_thread(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit or args.exc_value is None:
            return
        name = args.thread.name if args.thread else "?"
        logger.critical(
            f"Uncaught exception in thread {name}",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_uncaught
    threading.excepthook = log_thread


def _setup_logging(level: int) -> None:
    folder = log_dir()
    try:
        # Create the folder first: enable_file_logging takes a path that does not exist
        # yet for a file, and would name the log file like the folder.
        folder.mkdir(parents=True, exist_ok=True)
        enable_file_logging(
            folder / DEFAULT_LOG_FILE_NAME,
            level,
            max_bytes=LOG_MAX_BYTES,
            backup_count=LOG_BACKUP_COUNT,
        )
    except OSError as e:
        print(f"Cannot write the log file in {folder}: {e}", file=sys.stderr)
    if sys.stderr is not None:  # pythonw and a launcher without a terminal have none
        enable_console_logging(level, colored=False)


def run_tray(args: argparse.Namespace) -> int:
    _setup_logging(getattr(logging, args.log_level))
    _install_exception_logging()

    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from naneos.gui.instance import SingleInstance
        from naneos.gui.tray import TrayController
    except ImportError as e:
        logger.error(f"Qt is not available: {e}")
        print(MISSING_QT_HINT, file=sys.stderr)
        return 1

    from naneos.cli import installed_from
    from naneos.gui.integration import icon_file
    from naneos.manager import NaneosDeviceManager

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Naneos Devices")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)  # the tray keeps the app alive; windows come later
    app.setWindowIcon(QIcon(str(icon_file("png"))))
    if current_platform() == "darwin":
        from naneos.gui.macos import guard_event_click_count, hide_dock_icon

        hide_dock_icon()
        guard_event_click_count()

    instance = SingleInstance()
    if not instance.acquire():
        from naneos.gui.instance import send_command

        send_command("show")
        logger.info("Another naneos-gui is already running")
        return 0

    logger.info(f"naneos-gui {__version__} starting (installed from {installed_from()})")
    manager = NaneosDeviceManager(upload_active=not args.no_upload)
    controller = TrayController(app, manager, get_autostart(), __version__)
    instance.command_received.connect(controller.handle_command)

    def on_signal(signum: int, frame: Any) -> None:
        controller.request_quit()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    controller.start()
    try:
        return app.exec()
    finally:
        instance.release()
        logger.info("naneos-gui stopped")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    done = _run_setup_actions(args)
    if args.quit:
        return _quit_running(args.timeout)
    if done is not None:
        return done
    return run_tray(args)

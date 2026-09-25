"""The tray icon, its menu and the device manager that runs behind it."""

import queue
import time
from collections.abc import Sequence
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QAction, QCursor, QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from naneos.data_point import NaneosDeviceDataPoint
from naneos.gui.integration import Autostart, icon_file, log_dir
from naneos.gui.model import (
    DeviceLike,
    LastSeen,
    format_device_row,
    format_status,
    format_title,
    format_tooltip,
    sort_devices,
)
from naneos.logger import get_naneos_logger

logger = get_naneos_logger("naneos.gui.tray")

MAX_ROWS = 20  # device rows in the menu; more are summed up in the last one
POLL_MS = 1000
QUIT_POLL_MS = 200
QUIT_TIMEOUT_SECONDS = 25.0  # the manager needs up to ~20 s to disconnect BLE and flush
SESSION_END_JOIN_SECONDS = 4.0  # the OS gives a logging out app only a few seconds
TRAY_WARNING_AFTER_SECONDS = 30.0


class ManagerLike(Protocol):
    """The part of NaneosDeviceManager the tray uses."""

    @property
    def upload_active(self) -> bool: ...

    @property
    def pending_upload_count(self) -> int: ...

    @property
    def diagnostics_in_progress(self) -> bool: ...

    def register_live_queue(self, live_queue: "queue.Queue[NaneosDeviceDataPoint]") -> None: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def join(self, timeout: float | None = None) -> None: ...

    def is_alive(self) -> bool: ...

    def get_devices(self) -> Sequence[DeviceLike]: ...


class TrayController(QObject):
    """Owns the manager and keeps the menu in step with it.

    The menu is built once and only its actions change: rebuilding a QMenu that is
    open misbehaves on macOS and on the Linux D-Bus menu. Everything here runs on
    the GUI thread; the manager has its own threads, and bleak never runs here.
    """

    def __init__(
        self,
        app: QApplication,
        manager: ManagerLike,
        autostart: Autostart,
        version: str,
        quit_timeout_seconds: float = QUIT_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(app)
        self._app = app
        self._manager = manager
        self._autostart = autostart
        self._version = version
        self._quit_timeout = quit_timeout_seconds

        self._live: queue.Queue[NaneosDeviceDataPoint] = queue.Queue(maxsize=2000)
        self._seen = LastSeen()
        self._stopping = False
        self._gave_up = False  # Quit waited for the manager and it did not stop in time
        self._final_stop_done = False
        self._quit_deadline = 0.0
        self._started_at = time.monotonic()
        self._warned_no_tray = False
        self._death_logged = False

        self._tray = QSystemTrayIcon(QIcon(str(icon_file("png"))), self)
        self._menu = QMenu()  # owned by us: a tray icon does not take ownership
        self._build_menu()
        self._tray.setContextMenu(self._menu)

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self.refresh)
        self._quit_timer = QTimer(self)
        self._quit_timer.timeout.connect(self._check_stopped)
        # Python only runs its signal handlers (SIGTERM, Ctrl+C) when bytecode runs,
        # which a Qt event loop alone does not give it.
        self._signal_timer = QTimer(self)
        self._signal_timer.timeout.connect(lambda: None)

        app.aboutToQuit.connect(self._on_about_to_quit)
        app.commitDataRequest.connect(lambda *_: self._on_about_to_quit())

    # ------------------------------------------------------------ menu

    def _build_menu(self) -> None:
        menu = self._menu
        self._title_action = menu.addAction(format_title(self._version))
        self._title_action.setEnabled(False)
        self._status_action = menu.addAction("")
        self._status_action.setEnabled(False)
        menu.addSeparator()

        self._rows: list[QAction] = []
        for _ in range(MAX_ROWS):
            row = menu.addAction("")
            row.setEnabled(False)  # information only; later a submenu with commands
            row.setVisible(False)
            self._rows.append(row)
        menu.addSeparator()

        self._autostart_action = menu.addAction("Start at login")
        self._autostart_action.setCheckable(True)
        self._autostart_action.triggered.connect(self._set_autostart)
        self._log_action = menu.addAction("Open log folder")
        self._log_action.triggered.connect(self._open_log_folder)
        self._quit_action = menu.addAction("Quit")
        self._quit_action.triggered.connect(self.request_quit)

        menu.aboutToShow.connect(self._on_menu_about_to_show)

    def _on_menu_about_to_show(self) -> None:
        self._autostart_action.setChecked(self._safe_autostart_enabled())
        self.refresh()

    def _safe_autostart_enabled(self) -> bool:
        try:
            return self._autostart.enabled()
        except Exception as e:
            logger.warning(f"Cannot read the autostart setting: {e}")
            return False

    def _set_autostart(self, checked: bool) -> None:
        try:
            self._autostart.enable() if checked else self._autostart.disable()
        except Exception as e:
            logger.error(f"Cannot change the autostart setting: {e}")
            self._tray.showMessage("Naneos Devices", f"Could not change the setting: {e}")
        self._autostart_action.setChecked(self._safe_autostart_enabled())

    def _open_log_folder(self) -> None:
        folder = log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ------------------------------------------------------------ life cycle

    def start(self) -> None:
        self._manager.register_live_queue(self._live)
        self._manager.start()
        self._tray.show()
        self.refresh()
        self._poll_timer.start(POLL_MS)
        self._signal_timer.start(500)

    def refresh(self) -> None:
        """Bring the menu up to date. Runs every second and when the menu opens."""
        self._seen.drain(self._live)
        if self._stopping:
            return
        self._show_tray_when_available()

        devices = sort_devices(self._manager.get_devices())
        self._seen.forget_except(d.serial_number for d in devices)

        if not self._manager.is_alive():
            status = "Stopped – see log"
            if not self._death_logged:
                self._death_logged = True
                logger.error("The device manager stopped unexpectedly")
        else:
            status = format_status(
                self._manager.upload_active,
                self._manager.pending_upload_count,
                self._manager.diagnostics_in_progress,
            )
        self._status_action.setText(status)

        texts = [format_device_row(d, self._seen.age(d.serial_number)) for d in devices]
        if not texts:
            texts = ["No devices in reach"]
        if len(texts) > MAX_ROWS:
            texts = texts[: MAX_ROWS - 1] + [f"… and {len(texts) - MAX_ROWS + 1} more"]
        for i, row in enumerate(self._rows):
            row.setVisible(i < len(texts))
            if i < len(texts):
                row.setText(texts[i])

        self._tray.setToolTip(format_tooltip(self._version, len(devices)))

    def _show_tray_when_available(self) -> None:
        """A Linux desktop may start its tray after us; show the icon as soon as it exists."""
        if self._tray.isVisible():
            return
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.show()
        elif (
            not self._warned_no_tray
            and time.monotonic() - self._started_at > TRAY_WARNING_AFTER_SECONDS
        ):
            self._warned_no_tray = True
            logger.warning(
                "No system tray on this desktop. Devices are still read and uploaded. "
                "On GNOME install the 'AppIndicator and KStatusNotifierItem Support' extension."
            )

    def handle_command(self, command: str) -> None:
        """A command from another process, see instance.py."""
        if command == "quit":
            self.request_quit()
        elif command == "show":
            self.refresh()
            self._menu.popup(QCursor.pos())

    def request_quit(self) -> None:
        """Stop the manager without blocking the GUI, then leave the event loop."""
        if self._stopping:
            return
        self._stopping = True
        logger.info("Stopping")
        self._title_action.setText("Stopping…")
        self._status_action.setText("")
        for action in (self._autostart_action, self._log_action, self._quit_action):
            action.setEnabled(False)
        for row in self._rows:
            row.setVisible(False)
        self._tray.setToolTip("Naneos Devices – stopping")

        self._manager.stop()
        self._quit_deadline = time.monotonic() + self._quit_timeout
        self._quit_timer.start(QUIT_POLL_MS)

    def _check_stopped(self) -> None:
        if self._manager.is_alive() and time.monotonic() < self._quit_deadline:
            return
        self._quit_timer.stop()
        if self._manager.is_alive():
            self._gave_up = True
            logger.warning("The device manager did not stop in time, quitting anyway")
        self._tray.hide()
        self._app.quit()

    def _on_about_to_quit(self) -> None:
        """The OS is ending the session, or quit() was called: the last chance to stop.

        Called for both aboutToQuit and commitDataRequest, and it blocks the GUI thread, so
        it waits at most once, and not at all after Quit has already waited for nothing.
        """
        self._poll_timer.stop()
        if self._final_stop_done:
            return
        self._final_stop_done = True
        if self._gave_up or not self._manager.is_alive():
            return
        self._manager.stop()
        self._manager.join(timeout=SESSION_END_JOIN_SECONDS)

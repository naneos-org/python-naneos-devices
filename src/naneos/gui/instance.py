"""One tray app per user, and a way to talk to the running one.

Two managers would fight over the serial ports, so a second start must not
run. The first instance holds a lock file and listens on a local socket (a
named pipe on Windows). A second start, and `naneos-gui --quit`, send it one
line of text; the reply is "ok".

    ping    is anybody there
    show    a second start: pop up the menu
    quit    stop the manager and exit (used by the installers)
"""

import getpass
import time
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QStandardPaths, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from naneos.logger import get_naneos_logger

logger = get_naneos_logger("naneos.gui.instance")


def default_name() -> str:
    """One name per user: on Windows every user shares the pipe namespace."""
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return f"naneos-gui-{user}"


def _lock_path(name: str, lock_dir: Path | None) -> Path:
    temp = QStandardPaths.StandardLocation.TempLocation
    directory = lock_dir or Path(QStandardPaths.writableLocation(temp))
    return directory / f"{name}.lock"


class SingleInstance(QObject):
    """Holds the lock and answers the control commands of other processes."""

    command_received = Signal(str)

    def __init__(
        self, name: str | None = None, lock_dir: Path | None = None, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._name = name or default_name()
        # QLockFile removes a lock whose process is gone, so a crash never locks us out.
        self._lock = QLockFile(str(_lock_path(self._name, lock_dir)))
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._on_connection)

    def acquire(self) -> bool:
        """True if this process is now the one instance."""
        if not self._lock.tryLock(0):
            return False
        QLocalServer.removeServer(self._name)  # a socket file a crashed instance left behind
        if not self._server.listen(self._name):
            # Still the one instance, but --quit and a second start cannot reach it.
            logger.warning(f"Cannot listen on {self._name}: {self._server.errorString()}")
        return True

    def release(self) -> None:
        self._server.close()
        self._lock.unlock()

    def _on_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(socket.deleteLater)

    def _read(self, socket: QLocalSocket) -> None:
        if not socket.canReadLine():
            return
        command = bytes(socket.readLine().data()).decode(errors="replace").strip()
        socket.write(b"ok\n")
        socket.flush()
        socket.disconnectFromServer()
        logger.debug(f"Control command: {command}")
        self.command_received.emit(command)


def send_command(command: str, name: str | None = None, timeout_ms: int = 2000) -> str | None:
    """Send a command to the running instance. Its reply, or None if nobody answers."""
    socket = QLocalSocket()
    socket.connectToServer(name or default_name())
    if not socket.waitForConnected(timeout_ms):
        return None
    socket.write(command.encode() + b"\n")
    if not (socket.waitForBytesWritten(timeout_ms) and socket.waitForReadyRead(timeout_ms)):
        return None
    reply = bytes(socket.readAll().data()).decode(errors="replace").strip()
    socket.disconnectFromServer()
    return reply


def quit_running(
    timeout_seconds: float = 30.0, name: str | None = None, lock_dir: Path | None = None
) -> int:
    """Ask the running instance to quit and wait until it has let go of the lock.

    Returns 0 when it has stopped or was not running, 2 when it did not stop in time.
    """
    name = name or default_name()
    lock = QLockFile(str(_lock_path(name, lock_dir)))
    if send_command("quit", name) is None and lock.tryLock(0):
        lock.unlock()
        return 0  # nobody was running

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if lock.tryLock(200):
            lock.unlock()
            return 0
    return 2

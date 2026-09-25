"""Hardware-free tests of the tray app with Qt running offscreen and a fake manager."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import socket  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from collections.abc import Callable  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtNetwork import QLocalServer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from naneos.data_point import ConnectionType, DeviceType  # noqa: E402
from naneos.gui import tray as tray_module  # noqa: E402
from naneos.gui.instance import SingleInstance, quit_running, send_command  # noqa: E402
from naneos.gui.tray import MAX_ROWS, TrayController  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication(["naneos-test"])  # type: ignore[return-value]


@dataclass
class FakeDevice:
    serial_number: int | None
    device_type: DeviceType | None
    connection_type: ConnectionType


@dataclass
class FakePoint:
    serial_number: int | None


class FakeManager:
    """The part of NaneosDeviceManager the tray uses."""

    def __init__(self) -> None:
        self.devices: list[FakeDevice] = []
        self.upload_active = True
        self.pending_upload_count = 0
        self.diagnostics_in_progress = False
        self.alive = False
        self.live_queue = None
        self.stop_calls = 0
        self.join_timeouts: list[float | None] = []
        self.stops_by_itself = True  # False: a manager that hangs while stopping

    def register_live_queue(self, live_queue) -> None:
        self.live_queue = live_queue

    def start(self) -> None:
        self.alive = True

    def stop(self) -> None:
        self.stop_calls += 1
        if self.stops_by_itself:
            self.alive = False

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)

    def is_alive(self) -> bool:
        return self.alive

    def get_devices(self) -> list[FakeDevice]:
        return list(self.devices)


class FakeAutostart:
    def __init__(self) -> None:
        self.on = False
        self.fail = False

    def enabled(self) -> bool:
        return self.on

    def enable(self) -> None:
        if self.fail:
            raise OSError("read-only file system")
        self.on = True

    def disable(self) -> None:
        self.on = False


@pytest.fixture
def manager() -> FakeManager:
    return FakeManager()


@pytest.fixture
def autostart() -> FakeAutostart:
    return FakeAutostart()


@pytest.fixture
def controller(qapp, manager, autostart) -> TrayController:
    quit_calls: list[bool] = []
    controller = TrayController(qapp, manager, autostart, "2.1.0", quit_timeout_seconds=0.5)
    controller._app = SimpleNamespace(quit=lambda: quit_calls.append(True))  # type: ignore[assignment]
    controller.quit_calls = quit_calls  # type: ignore[attr-defined]
    controller.start()
    yield controller
    controller._poll_timer.stop()
    controller._quit_timer.stop()
    controller._signal_timer.stop()


def _texts(controller: TrayController) -> list[str]:
    return [row.text() for row in controller._rows if row.isVisible()]


def _pump(qapp: QApplication, until: Callable[[], bool], seconds: float = 5.0) -> bool:
    """Run the event loop until a condition holds."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        if until():
            return True
        time.sleep(0.01)
    return until()


# ---------------------------------------------------------------- the menu


def test_menu_shows_the_devices_like_the_mock(controller, manager) -> None:
    manager.devices = [
        FakeDevice(8764, DeviceType.P2PRO, ConnectionType.SERIAL),
        FakeDevice(8123, DeviceType.P2, ConnectionType.CONNECTED),
        FakeDevice(8617, DeviceType.P2, ConnectionType.SERIAL),
    ]
    for serial in (8764, 8617, 8123):
        manager.live_queue.put(FakePoint(serial))

    controller.refresh()

    assert controller._title_action.text() == "naneos devices 2.1.0"
    assert controller._status_action.text() == "Upload: on · 0 pending"
    assert _texts(controller) == [
        "P2      SN8123  BLE  0 s",
        "P2      SN8617  USB  0 s",
        "P2 Pro  SN8764  USB  0 s",
    ]
    assert controller._tray.toolTip() == "naneos devices 2.1.0 – 3 devices"
    assert [a.text() for a in controller._menu.actions() if a.isVisible() and a.text()][-3:] == [
        "Start at login",
        "Open log folder",
        "Quit",
    ]


def test_menu_shows_no_data_yet_and_says_so_when_no_device_is_in_reach(controller, manager) -> None:
    controller.refresh()
    assert _texts(controller) == ["No devices in reach"]

    manager.devices = [FakeDevice(8617, DeviceType.P2, ConnectionType.SERIAL)]
    controller.refresh()
    assert _texts(controller) == ["P2      SN8617  USB  –"]  # connected, no data point yet


def test_a_device_that_leaves_is_dropped_and_starts_again_without_an_age(
    controller, manager
) -> None:
    device = FakeDevice(8617, DeviceType.P2, ConnectionType.SERIAL)
    manager.devices = [device]
    manager.live_queue.put(FakePoint(8617))
    controller.refresh()
    assert _texts(controller) == ["P2      SN8617  USB  0 s"]

    manager.devices = []
    controller.refresh()
    manager.devices = [device]
    controller.refresh()

    assert _texts(controller) == ["P2      SN8617  USB  –"]


def test_menu_sums_up_devices_beyond_the_rows_it_has(controller, manager) -> None:
    manager.devices = [
        FakeDevice(1000 + i, DeviceType.P2, ConnectionType.CONNECTED) for i in range(MAX_ROWS + 5)
    ]

    controller.refresh()

    texts = _texts(controller)
    assert len(texts) == MAX_ROWS
    assert texts[-1] == "… and 6 more"


def test_status_line_follows_the_manager(controller, manager) -> None:
    manager.upload_active = False
    controller.refresh()
    assert controller._status_action.text() == "Upload: off"

    manager.upload_active = True
    manager.pending_upload_count = 7
    manager.diagnostics_in_progress = True
    controller.refresh()
    assert controller._status_action.text() == "Upload: on · 7 pending · diagnostics"


def test_status_line_says_when_the_manager_died(controller, manager) -> None:
    manager.alive = False
    controller.refresh()
    assert controller._status_action.text() == "Stopped – see log"


def test_the_live_queue_is_registered_and_the_manager_started(controller, manager) -> None:
    assert manager.live_queue is not None
    assert manager.live_queue.maxsize > 0  # bounded: a stuck GUI must not fill the memory
    assert manager.alive


# ---------------------------------------------------------------- start at login


def test_start_at_login_shows_the_current_setting_and_toggles_it(controller, autostart) -> None:
    autostart.on = True
    controller._on_menu_about_to_show()
    assert controller._autostart_action.isChecked()

    controller._set_autostart(False)
    assert not autostart.on
    assert not controller._autostart_action.isChecked()

    controller._set_autostart(True)
    assert autostart.on
    assert controller._autostart_action.isChecked()


def test_start_at_login_that_fails_is_reported_and_not_shown_as_on(controller, autostart) -> None:
    autostart.fail = True

    controller._set_autostart(True)

    assert not autostart.on
    assert not controller._autostart_action.isChecked()


# ---------------------------------------------------------------- quitting


def test_quit_stops_the_manager_and_leaves_the_event_loop(qapp, controller, manager) -> None:
    controller.request_quit()

    assert manager.stop_calls == 1
    assert controller._title_action.text() == "Stopping…"
    assert not controller._quit_action.isEnabled()
    assert _pump(qapp, lambda: bool(controller.quit_calls))


def test_quit_waits_for_a_manager_that_takes_time(qapp, controller, manager) -> None:
    manager.stops_by_itself = False
    controller.request_quit()
    _pump(qapp, lambda: False, seconds=0.3)
    assert not controller.quit_calls  # still stopping

    manager.alive = False
    assert _pump(qapp, lambda: bool(controller.quit_calls))


def test_quit_does_not_wait_for_ever(qapp, controller, manager) -> None:
    manager.stops_by_itself = False  # never stops; the controller has a 0.5 s limit here

    controller.request_quit()

    assert _pump(qapp, lambda: bool(controller.quit_calls), seconds=3)


def test_quit_twice_stops_once(controller, manager) -> None:
    controller.request_quit()
    controller.request_quit()
    controller.handle_command("quit")
    assert manager.stop_calls == 1


def test_quit_command_from_another_process_quits(qapp, controller, manager) -> None:
    controller.handle_command("quit")
    assert _pump(qapp, lambda: bool(controller.quit_calls))


def test_the_session_ending_stops_the_manager_with_a_short_wait(controller, manager) -> None:
    manager.stops_by_itself = False

    controller._on_about_to_quit()

    assert manager.stop_calls == 1
    assert manager.join_timeouts == [tray_module.SESSION_END_JOIN_SECONDS]


def test_the_session_ending_waits_only_once(controller, manager) -> None:
    manager.stops_by_itself = False

    controller._on_about_to_quit()  # aboutToQuit and commitDataRequest both end up here
    controller._on_about_to_quit()

    assert manager.join_timeouts == [tray_module.SESSION_END_JOIN_SECONDS]


def test_no_second_wait_after_quit_gave_up_on_the_manager(qapp, controller, manager) -> None:
    manager.stops_by_itself = False
    controller.request_quit()
    assert _pump(qapp, lambda: bool(controller.quit_calls), seconds=3)  # gave up after 0.5 s

    controller._on_about_to_quit()

    assert manager.join_timeouts == []


def test_the_menu_is_not_refreshed_while_stopping(controller, manager) -> None:
    controller.request_quit()
    manager.devices = [FakeDevice(1, DeviceType.P2, ConnectionType.SERIAL)]
    controller.refresh()
    assert _texts(controller) == []


# ---------------------------------------------------------------- one instance
#
# The client of these tests is a separate process, like the real ones (a second
# start, `naneos-gui --quit`). A client thread in the test process would keep the
# GIL during its blocking Qt call, so the server slot in the main thread could not run.


@pytest.fixture
def unique_name() -> str:
    return f"naneos-test-{uuid.uuid4().hex[:8]}"


def _client(code: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-c", "import os; os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n" + code],
        stdout=subprocess.PIPE,
        text=True,
    )


def _finish(qapp: QApplication, client: subprocess.Popen[str], seconds: float = 30.0) -> str:
    """Serve the main thread's event loop until the client process ends; its output."""
    assert _pump(qapp, lambda: client.poll() is not None, seconds), "the client did not end"
    assert client.stdout is not None
    return client.stdout.read().strip()


def _send(name: str, command: str) -> subprocess.Popen[str]:
    return _client(
        "from naneos.gui.instance import send_command\n"
        f"print(send_command({command!r}, {name!r}))\n"
    )


def _quit_running(name: str, lock_dir, timeout: float) -> subprocess.Popen[str]:
    return _client(
        "from pathlib import Path\n"
        "from naneos.gui.instance import quit_running\n"
        f"print(quit_running({timeout!r}, {name!r}, Path({str(lock_dir)!r})))\n"
    )


def test_only_one_instance_gets_the_lock(qapp, unique_name, tmp_path) -> None:
    first = SingleInstance(unique_name, tmp_path)
    second = SingleInstance(unique_name, tmp_path)
    try:
        assert first.acquire()
        assert not second.acquire()

        first.release()
        assert second.acquire()
    finally:
        first.release()
        second.release()


def test_a_command_reaches_the_running_instance(qapp, unique_name, tmp_path) -> None:
    instance = SingleInstance(unique_name, tmp_path)
    received: list[str] = []
    instance.command_received.connect(received.append)
    assert instance.acquire()
    try:
        assert _finish(qapp, _send(unique_name, "show")) == "ok"
        assert received == ["show"]
    finally:
        instance.release()


def test_nobody_answers_when_no_instance_runs(qapp, unique_name) -> None:
    assert send_command("ping", unique_name, timeout_ms=200) is None


@pytest.mark.skipif(sys.platform == "win32", reason="a named pipe leaves no file behind")
def test_a_socket_file_left_by_a_crashed_instance_does_not_block_the_next(
    qapp, unique_name, tmp_path
) -> None:
    probe = QLocalServer()
    assert probe.listen(unique_name)
    path = probe.fullServerName()
    probe.close()
    with socket.socket(socket.AF_UNIX) as stale:
        stale.bind(path)  # the file stays after close, like after a crash
    assert os.path.exists(path)

    instance = SingleInstance(unique_name, tmp_path)
    try:
        assert instance.acquire()
        assert _finish(qapp, _send(unique_name, "ping")) == "ok"
    finally:
        instance.release()


def test_quit_running_with_nobody_running_returns_at_once(qapp, unique_name, tmp_path) -> None:
    started = time.monotonic()
    assert quit_running(5, unique_name, tmp_path) == 0
    assert time.monotonic() - started < 3


def test_quit_running_waits_until_the_instance_let_go_of_the_lock(
    qapp, unique_name, tmp_path
) -> None:
    instance = SingleInstance(unique_name, tmp_path)
    received: list[str] = []
    instance.command_received.connect(received.append)
    # what the tray does after "quit": stop, and only then let go of the lock
    instance.command_received.connect(lambda c: instance.release() if c == "quit" else None)
    assert instance.acquire()
    try:
        assert _finish(qapp, _quit_running(unique_name, tmp_path, 10)) == "0"
        assert received == ["quit"]
    finally:
        instance.release()


def test_quit_running_reports_an_instance_that_does_not_stop(qapp, unique_name, tmp_path) -> None:
    instance = SingleInstance(unique_name, tmp_path)
    received: list[str] = []
    instance.command_received.connect(received.append)
    assert instance.acquire()  # holds the lock and answers, but never quits
    try:
        assert _finish(qapp, _quit_running(unique_name, tmp_path, 1)) == "2"
        assert received == ["quit"]
    finally:
        instance.release()

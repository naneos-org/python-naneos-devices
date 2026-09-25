"""Hardware-free tests for putting a P2 Pro into size distribution mode over BLE.

The USB connect does it on every connect; so does the BLE connect now, with the one command
M0004! (measured on a real P2 Pro, see PartectorBleConnection.P2PRO_MODE_COMMANDS).
"""

import asyncio
import logging
from types import SimpleNamespace

import pytest
from bleak.backends.device import BLEDevice

from naneos.ble.partector import connection as module
from naneos.ble.partector.commands import BleCommandChannel
from naneos.ble.partector.connection import PartectorBleConnection
from naneos.data_point import DeviceType
from naneos.manager import NaneosDeviceManager

READ = PartectorBleConnection.CHAR_UUIDS["read"]


def _frame(text: str) -> bytes:
    return f"{text}\r\n".encode().ljust(20, b" ")


class _Services:
    def get_service(self, uuid):
        return object()

    def get_characteristic(self, uuid):
        return object()


class _Client:
    """A BleakClient that answers f? and name? like a device and records every write."""

    def __init__(self, name: str | None, firmware: str = "420") -> None:
        self.is_connected = False
        self.services = _Services()
        self.callbacks: dict = {}
        self.answers = {"f?": firmware}
        if name is not None:
            self.answers["name?"] = name
        self.written: list[str] = []  # the writes that worked
        self.attempts: list[str] = []  # every write, also the ones that failed
        self.failing: set[str] = set()
        self.no_read_characteristic = False

    async def connect(self, timeout=None):
        self.is_connected = True

    async def start_notify(self, uuid, callback):
        if uuid == READ and self.no_read_characteristic:
            raise OSError("no such characteristic")
        self.callbacks[uuid] = callback

    async def write_gatt_char(self, uuid, data, response=False):
        command = bytes(data).decode()
        self.attempts.append(command)
        if command in self.failing:
            raise OSError("write failed")
        self.written.append(command)
        if command in self.answers:
            self.callbacks[READ](None, bytearray(_frame(self.answers[command])))

    async def stop_notify(self, uuid):
        pass

    async def disconnect(self):
        self.is_connected = False


@pytest.fixture
def make(monkeypatch):
    """A fake device: make(name="P2pro", **connection_arguments) -> (connection, client)."""
    loops: list[asyncio.AbstractEventLoop] = []

    def factory(name: str | None = "P2pro", firmware: str = "420", **kwargs):
        client = _Client(name, firmware)
        monkeypatch.setattr(PartectorBleConnection, "_new_client", lambda self: client)
        loop = asyncio.new_event_loop()
        loops.append(loop)
        device = BLEDevice("AA:BB:CC:DD:EE:FF", "P2", None)
        conn = PartectorBleConnection(
            device, loop, 8617, PartectorBleConnection.create_connection_queue(), **kwargs
        )
        return conn, client

    yield factory
    for loop in loops:
        loop.close()


async def _connect(conn: PartectorBleConnection) -> None:
    """One connect attempt, then wait for the tasks it starts."""
    conn._loop = asyncio.get_running_loop()
    await conn._try_connect()
    for task in (conn._info_task, conn._mode_task):
        if task is not None:
            await task


def test_a_p2_pro_is_switched_after_its_name_is_known(make) -> None:
    conn, client = make("P2pro")

    asyncio.run(_connect(conn))

    assert conn.device_type == DeviceType.P2PRO
    assert client.written == ["f?", "name?", "M0004!"]


def test_a_p2_gets_no_mode_command(make) -> None:
    conn, client = make("P2")

    asyncio.run(_connect(conn))

    assert conn.device_type == DeviceType.P2
    assert client.written == ["f?", "name?"]


def test_the_switch_is_sent_again_at_every_connect_without_asking_the_name_again(make) -> None:
    conn, client = make("P2pro")

    async def scenario() -> None:
        await _connect(conn)
        client.is_connected = False  # the link dropped and came back
        await _connect(conn)
        client.is_connected = False
        await _connect(conn)

    asyncio.run(scenario())

    assert client.written == ["f?", "name?", "M0004!", "M0004!", "M0004!"]


def test_the_switch_can_be_turned_off(make) -> None:
    conn, client = make("P2pro", p2pro_mode=False)

    asyncio.run(_connect(conn))

    assert conn._mode_task is None
    assert client.written == ["f?", "name?"]


def test_a_guard_that_says_no_keeps_the_mode_alone_and_is_asked_at_every_connect(make) -> None:
    answers = iter([False, True])
    asked: list[int] = []

    def guard(serial: int) -> bool:
        asked.append(serial)
        return next(answers)

    conn, client = make("P2pro", p2pro_mode_guard=guard)

    async def scenario() -> None:
        await _connect(conn)
        assert "M0004!" not in client.written  # USB has this device
        client.is_connected = False
        await _connect(conn)

    asyncio.run(scenario())

    assert asked == [8617, 8617]
    assert client.written.count("M0004!") == 1


def test_a_device_family_that_is_not_known_is_not_switched(make, monkeypatch) -> None:
    monkeypatch.setattr(BleCommandChannel, "QUERY_TIMEOUT_SECONDS", 0.05)
    conn, client = make(None)  # answers nothing to name?
    client.answers.clear()  # and nothing to f? either

    asyncio.run(_connect(conn))

    assert client.written == ["f?"]  # the query gave up, nothing else was written


def test_a_p2_pro_recognised_by_its_data_is_switched_even_if_the_name_query_got_no_answer(
    make, monkeypatch
) -> None:
    monkeypatch.setattr(BleCommandChannel, "QUERY_TIMEOUT_SECONDS", 0.05)
    conn, client = make(None)
    client.answers.clear()
    conn._device_type = DeviceType.P2PRO  # what the first size distribution frame does

    asyncio.run(_connect(conn))

    assert client.written == ["f?", "M0004!"]


def test_a_failed_switch_costs_the_mode_not_the_link_and_is_tried_at_the_next_connect(
    make, caplog
) -> None:
    conn, client = make("P2pro")
    client.failing = {"M0004!"}

    async def scenario() -> None:
        with caplog.at_level(logging.INFO, logger="naneos"):
            await _connect(conn)
        assert client.is_connected  # the link is fine
        assert client.written == ["f?", "name?"]
        assert client.attempts[-1] == "M0004!"

        client.failing = set()
        client.is_connected = False
        await _connect(conn)

    asyncio.run(scenario())

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("could not put the P2 Pro into size distribution mode" in m for m in warnings)
    assert client.written[-1] == "M0004!"


def test_a_guard_that_raises_does_not_break_the_connect(make, caplog) -> None:
    def guard(serial: int) -> bool:
        raise RuntimeError("boom")

    conn, client = make("P2pro", p2pro_mode_guard=guard)

    with caplog.at_level(logging.WARNING, logger="naneos"):
        asyncio.run(_connect(conn))

    assert client.written == ["f?", "name?"]
    assert any("boom" in r.getMessage() for r in caplog.records)


def test_a_device_without_the_command_characteristics_is_not_switched(make) -> None:
    conn, client = make("P2pro")
    client.no_read_characteristic = True

    asyncio.run(_connect(conn))

    assert conn._mode_task is None
    assert client.attempts == []


def test_a_switch_that_waits_behind_a_running_readout_can_be_cancelled(make) -> None:
    conn, client = make("P2pro")
    conn._device_type = DeviceType.P2PRO
    conn._firmware_version = 420

    async def scenario() -> None:
        conn._loop = asyncio.get_running_loop()
        await conn._commands.lock.acquire()  # what a diagnostics readout holds for ~50 s
        await conn._try_connect()
        await asyncio.sleep(0)
        assert conn._mode_task is not None and not conn._mode_task.done()

        await conn._stop_mode_task()

        assert conn._mode_task.cancelled()
        conn._commands.lock.release()

    asyncio.run(scenario())

    assert client.written == []


def test_a_switch_left_over_from_the_previous_link_is_replaced_not_doubled(make) -> None:
    conn, client = make("P2pro")
    conn._device_type = DeviceType.P2PRO
    conn._firmware_version = 420

    async def scenario() -> None:
        conn._loop = asyncio.get_running_loop()
        await conn._commands.lock.acquire()
        await conn._try_connect()
        first = conn._mode_task
        await asyncio.sleep(0)

        conn._start_p2pro_mode()  # the next connect
        await asyncio.sleep(0)
        assert first is not None and first.cancelled()

        conn._commands.lock.release()
        assert conn._mode_task is not None
        await conn._mode_task

    asyncio.run(scenario())

    assert client.written == ["M0004!"]


def test_the_command_is_the_size_distribution_mode_only() -> None:
    """X0006! is the format of the USB line and does not exist over BLE; A0002! is a setting."""
    assert PartectorBleConnection.P2PRO_MODE_COMMANDS == ("M0004!",)
    assert module.DeviceType.P2PRO is DeviceType.P2PRO


# ---------------------------------------------------------------- NaneosDeviceManager


def _manager(**kwargs) -> NaneosDeviceManager:
    return NaneosDeviceManager(use_serial=False, use_ble=False, upload_active=False, **kwargs)


def test_usb_decides_the_mode_of_a_device_it_has_and_while_a_rate_is_set() -> None:
    manager = _manager()
    assert manager._ble_may_set_p2pro_mode(8134) is True  # no USB at all

    manager._manager_serial = SimpleNamespace(get_connected_serial_numbers=lambda: [8134, None])  # type: ignore[assignment]
    assert manager._ble_may_set_p2pro_mode(8134) is False  # this one is on USB
    assert manager._ble_may_set_p2pro_mode(8617) is True  # this one is not

    manager.sample_rate_hz = 10  # a rate means the plain P2 mode, on purpose
    assert manager._ble_may_set_p2pro_mode(8617) is False
    manager.sample_rate_hz = None
    assert manager._ble_may_set_p2pro_mode(8617) is True


def test_the_device_manager_hands_the_option_and_the_guard_to_the_ble_manager(monkeypatch) -> None:
    made: list[tuple] = []

    class FakeBleManager:
        DEFAULT_MAX_LINKS = 7

        def __init__(self, *args) -> None:
            made.append(args)

        def start(self) -> None:
            pass

    monkeypatch.setattr("naneos.manager.PartectorBleManager", FakeBleManager)

    for wanted in (True, False):
        manager = NaneosDeviceManager(
            use_serial=False, use_ble=True, upload_active=False, ble_p2pro_mode=wanted
        )
        manager._loop_ble_manager()

        serials, max_links, listener, p2pro_mode, guard = made[-1]
        assert p2pro_mode is wanted
        assert guard == manager._ble_may_set_p2pro_mode

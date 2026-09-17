"""Hardware-free tests for the reconnect logic of PartectorBleConnection.

A fake BleakClient is injected through _new_client(), so the watchdog, the
connect attempt and the error handling run without an adapter.
"""

import asyncio
import time

import pytest
from bleak.backends.device import BLEDevice

from naneos.ble import connection as module
from naneos.ble.connection import PartectorBleConnection


class _FakeServices:
    def get_service(self, uuid):
        return object()

    def get_characteristic(self, uuid):
        return object()


class _FakeClient:
    def __init__(self) -> None:
        self.is_connected = False
        self.services = _FakeServices()
        self.calls: list[str] = []
        self.callbacks: dict = {}
        self.answer: bytes | list[bytes] | None = None  # sent on "read" after every write

    async def connect(self, timeout=None):
        self.calls.append("connect")
        self.is_connected = True

    async def start_notify(self, uuid, callback):
        self.calls.append(f"notify:{uuid[6:8]}")
        self.callbacks[uuid] = callback

    async def write_gatt_char(self, uuid, data, response=False):
        self.calls.append(f"write:{bytes(data).decode()}")
        if self.answer is not None:
            frames = self.answer if isinstance(self.answer, list) else [self.answer]
            for frame in frames:
                self.callbacks[PartectorBleConnection.CHAR_UUIDS["read"]](None, bytearray(frame))

    async def stop_notify(self, uuid):
        self.calls.append(f"stop:{uuid[6:8]}")

    async def disconnect(self):
        self.calls.append("disconnect")
        self.is_connected = False


@pytest.fixture
def connection(monkeypatch) -> PartectorBleConnection:
    monkeypatch.setattr(PartectorBleConnection, "_new_client", lambda self: _FakeClient())

    async def no_sleep(seconds):  # the error handler pauses 0.5 s per failure
        return None

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)

    loop = asyncio.new_event_loop()
    device = BLEDevice("AA:BB:CC:DD:EE:FF", "P2", None)
    conn = PartectorBleConnection(
        device, loop, 8617, PartectorBleConnection.create_connection_queue()
    )
    conn._firmware_version = 422  # known already, so a connect starts no query of its own
    yield conn
    loop.close()


def test_connect_attempt_subscribes_and_resets_the_failure_counters(connection) -> None:
    connection._reconnect_attempt = 3
    connection._gatt_error_count = 2

    asyncio.run(connection._try_connect())

    client = connection._client
    assert client.is_connected
    assert client.calls == ["connect", "notify:80", "notify:81", "notify:84", "notify:83"]
    assert connection._reconnect_attempt == 0
    assert connection._gatt_error_count == 0


def test_watchdog_drops_a_link_reported_dead_by_the_callback(connection) -> None:
    asyncio.run(connection._try_connect())
    connection._disconnect_callback(connection._client)

    dropped = asyncio.run(connection._watchdog())

    assert dropped
    assert not connection._client.is_connected
    assert connection._backoff_remaining == 5  # first backoff step
    assert connection._disconnected_flag is False


def test_watchdog_drops_a_link_that_stopped_sending(connection) -> None:
    asyncio.run(connection._try_connect())
    assert not asyncio.run(connection._watchdog())  # fresh link, nothing to do

    connection._last_aux_data_ts = time.time() - connection.DATA_TIMEOUT_SECONDS - 1
    assert asyncio.run(connection._watchdog())
    assert not connection._client.is_connected
    assert "disconnect" in connection._client.calls


def test_connect_errors_back_off_and_recreate_the_client_when_needed(connection) -> None:
    first_client = connection._client

    asyncio.run(connection._handle_connect_error(TimeoutError()))
    assert connection._backoff_remaining == 5
    assert connection._client is first_client

    asyncio.run(connection._handle_connect_error(RuntimeError("GATT failure")))
    assert connection._gatt_error_count == 1
    assert connection._client is first_client  # recreated only from the second GATT error

    asyncio.run(connection._handle_connect_error(RuntimeError("device unreachable")))
    assert connection._gatt_error_count == 2
    assert connection._client is not first_client

    recreated = connection._client
    asyncio.run(connection._handle_connect_error(RuntimeError("something else")))
    assert connection._client is not recreated  # unknown errors always start fresh
    assert connection._backoff_remaining == 30  # capped at MAX_BACKOFF_SECONDS


def test_disconnect_stops_every_notification_once(connection) -> None:
    asyncio.run(connection._try_connect())

    asyncio.run(connection._disconnect_gracefully())

    assert connection._client.calls[-5:] == [
        "stop:80", "stop:81", "stop:84", "stop:83", "disconnect",
    ]  # fmt: skip
    asyncio.run(connection._disconnect_gracefully())  # already down: nothing more
    assert connection._client.calls.count("disconnect") == 1


def test_query_returns_the_answer_without_its_padding(connection) -> None:
    async def scenario() -> None:
        await connection._try_connect()
        connection._client.answer = b"8617\r\n              "
        assert await connection.query("N?") == ["8617"]
        assert connection._client.calls[-1] == "write:N?"

        connection._client.answer = [b"a\tb\tc and some more te", b"xt\r\n              "]
        assert await connection.query("long?") == ["a", "b", "c and some more text"]

    asyncio.run(scenario())


def test_query_times_out_and_a_late_answer_is_not_taken_for_the_next_one(connection) -> None:
    async def scenario() -> None:
        await connection._try_connect()
        with pytest.raises(TimeoutError):
            await connection.query("N?", timeout=0.01)

        read = connection._client.callbacks[PartectorBleConnection.CHAR_UUIDS["read"]]
        read(None, bytearray(b"8617\r\n              "))  # the late answer
        connection._client.answer = b"422\r\n               "
        assert await connection.query("f?") == ["422"]

    asyncio.run(scenario())


def test_commands_need_a_link_and_fit_into_one_write(connection) -> None:
    async def scenario() -> None:
        with pytest.raises(ConnectionError):
            await connection.write("X0001!")

        await connection._try_connect()
        await connection.write("A0002!")
        assert connection._client.calls[-1] == "write:A0002!"
        with pytest.raises(ValueError):
            await connection.write("x" * 21)

    asyncio.run(scenario())


def test_firmware_version_is_read_after_the_connect_and_put_on_the_points(connection) -> None:
    async def scenario() -> None:
        connection._firmware_version = None
        connection._loop = asyncio.get_running_loop()
        connection._client.answer = b"424\r\n               "
        await connection._try_connect()
        await connection._info_task

        assert connection.firmware_version == 424
        assert connection.device_type is None  # "424" is no device name
        connection._emit_data_point()  # closes the point in progress, starts the next
        connection._emit_data_point()
        connection._queue.get_nowait()
        assert connection._queue.get_nowait().firmware_version == 424

    asyncio.run(scenario())

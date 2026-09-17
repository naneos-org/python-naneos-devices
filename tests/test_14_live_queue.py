"""Hardware-free tests for the live data stream of NaneosDeviceManager."""

import asyncio
import queue
import time

from bleak.backends.device import BLEDevice
from fake_transport import FakeTransport

from naneos import NaneosDeviceManager
from naneos.ble.partector.connection import PartectorBleConnection
from naneos.data_point import ConnectionType, NaneosDeviceDataPoint
from naneos.usb.partector import layouts
from naneos.usb.partector.device import Partector2


def _point(serial_number: int, connection: ConnectionType, ldsa: float = 1.0):
    return NaneosDeviceDataPoint(
        unix_timestamp=1000, serial_number=serial_number, connection_type=connection, ldsa=ldsa
    )


def _manager() -> NaneosDeviceManager:
    return NaneosDeviceManager(use_serial=False, use_ble=False, upload_active=False)


class _SerialManagerStub:
    def get_connected_serial_numbers(self) -> list[int]:
        return [8617]


def test_points_reach_the_live_queue_only_while_one_is_registered() -> None:
    manager = _manager()
    manager._on_live_point(_point(1, ConnectionType.SERIAL))  # nobody listens: no error

    live: queue.Queue = queue.Queue(maxsize=10)
    manager.register_live_queue(live)
    manager._on_live_point(_point(1, ConnectionType.SERIAL))
    manager._on_live_point(_point(2, ConnectionType.CONNECTED))
    assert [live.get_nowait().serial_number for _ in range(2)] == [1, 2]

    manager.unregister_live_queue()
    manager._on_live_point(_point(1, ConnectionType.SERIAL))
    assert live.empty()


def test_a_device_on_usb_and_ble_delivers_its_usb_points_only() -> None:
    manager = _manager()
    manager._manager_serial = _SerialManagerStub()  # type: ignore[assignment]
    live: queue.Queue = queue.Queue(maxsize=10)
    manager.register_live_queue(live)

    manager._on_live_point(_point(8617, ConnectionType.CONNECTED))  # also on USB: skipped
    manager._on_live_point(_point(8617, ConnectionType.SERIAL))
    manager._on_live_point(_point(8764, ConnectionType.CONNECTED))  # BLE only: kept

    points = [live.get_nowait() for _ in range(2)]
    assert [(p.serial_number, p.connection_type) for p in points] == [
        (8617, ConnectionType.SERIAL),
        (8764, ConnectionType.CONNECTED),
    ]
    assert live.empty()


def test_a_full_live_queue_drops_the_oldest_point_and_never_blocks() -> None:
    manager = _manager()
    live: queue.Queue = queue.Queue(maxsize=3)
    manager.register_live_queue(live)

    started = time.monotonic()
    for i in range(10):
        manager._on_live_point(_point(1, ConnectionType.SERIAL, ldsa=float(i)))

    assert time.monotonic() - started < 0.5
    assert [live.get_nowait().ldsa for _ in range(3)] == [7.0, 8.0, 9.0]
    assert manager.live_points_dropped == 7


def test_usb_device_pushes_every_point_and_survives_a_failing_listener() -> None:
    received: list[NaneosDeviceDataPoint] = []

    def listener(point: NaneosDeviceDataPoint) -> None:
        received.append(point)
        if len(received) == 1:
            raise RuntimeError("consumer bug")

    transport = FakeTransport()
    device = Partector2(
        transport=transport,  # type: ignore[arg-type]
        gain_test_active=False,
        output_pulse_diagnostics=False,
        point_listener=listener,
    )
    try:
        for _ in range(3):
            transport.emit(len(layouts.PARTECTOR2_DATA_STRUCTURE) - 1)
        deadline = time.time() + 2
        while len(received) < 3 and time.time() < deadline:
            time.sleep(0.01)

        assert len(received) == 3  # the reader thread kept going after the exception
        assert device.is_connected
        assert len(device.get_data()) == 3  # the pull API still gets everything
    finally:
        device.close()


def test_ble_link_pushes_published_points_but_not_the_one_without_a_serial_number(
    monkeypatch,
) -> None:
    monkeypatch.setattr(PartectorBleConnection, "_new_client", lambda self: object())
    received: list[NaneosDeviceDataPoint] = []
    loop = asyncio.new_event_loop()
    try:
        connection = PartectorBleConnection(
            BLEDevice("AA:BB:CC:DD:EE:FF", "P2", None),
            loop,
            8617,
            PartectorBleConnection.create_connection_queue(),
            point_listener=received.append,
        )
        connection._emit_data_point()  # the point in progress at connect: no serial number
        connection._emit_data_point()
    finally:
        loop.close()

    assert [p.serial_number for p in received] == [8617]
    assert received[0].connection_type == ConnectionType.CONNECTED

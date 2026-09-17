"""Hardware-free tests for the link bookkeeping of PartectorBleManager."""

import asyncio

from naneos.data_point import ConnectionType, DeviceType, NaneosDeviceDataPoint
from naneos.partector_ble.partector_ble_manager import BleLink, PartectorBleManager


class _FakeConnection:
    def __init__(self, connected: bool) -> None:
        self.is_connected = connected


async def _idle() -> None:
    await asyncio.sleep(0)


def _manager_with_links() -> PartectorBleManager:
    manager = PartectorBleManager()
    loop = asyncio.new_event_loop()
    try:
        manager._links = {
            1: BleLink(loop.create_task(_idle()), _FakeConnection(True)),  # type: ignore[arg-type]
            2: BleLink(loop.create_task(_idle()), _FakeConnection(True)),  # type: ignore[arg-type]
            3: BleLink(loop.create_task(_idle()), _FakeConnection(False)),  # type: ignore[arg-type]
            4: BleLink(loop.create_task(_idle()), None),  # type: ignore[arg-type]
            5: BleLink(loop.create_task(_idle()), _FakeConnection(True)),  # type: ignore[arg-type]
        }
        loop.run_until_complete(asyncio.gather(*(link.task for link in manager._links.values())))
    finally:
        loop.close()
    return manager


def test_only_live_links_are_reported() -> None:
    manager = _manager_with_links()
    manager._links[1].device = "handle-1"  # type: ignore[assignment]
    manager._links[3].device = "handle-3"  # type: ignore[assignment]

    assert manager.get_connected_serial_numbers() == [1, 2, 5]
    assert manager.get_devices() == ["handle-1"]  # 3 is retrying, 2 and 5 have no handle yet


def test_points_from_the_links_are_buffered_per_device() -> None:
    manager = _manager_with_links()

    point = NaneosDeviceDataPoint(
        unix_timestamp=1000,
        serial_number=5,
        connection_type=ConnectionType.CONNECTED,
        device_type=DeviceType.P2PRO,
        ldsa=1.0,
    )
    manager._queue_connection.put_nowait(point)
    asyncio.run(manager._connection_queue_routine())

    assert list(manager.get_data()[5]["ldsa"]) == [1.0]
    assert manager.get_data() == {}


def test_finished_tasks_are_forgotten() -> None:
    manager = _manager_with_links()  # every task has already finished

    manager._forget_finished_links()

    assert manager._links == {}

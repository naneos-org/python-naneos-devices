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
            1: BleLink(loop.create_task(_idle()), _FakeConnection(True), DeviceType.P2),  # type: ignore[arg-type]
            2: BleLink(loop.create_task(_idle()), _FakeConnection(True), DeviceType.P2PRO),  # type: ignore[arg-type]
            3: BleLink(loop.create_task(_idle()), _FakeConnection(False), DeviceType.P2PRO),  # type: ignore[arg-type]
            4: BleLink(loop.create_task(_idle()), None, None),  # type: ignore[arg-type]
            5: BleLink(loop.create_task(_idle()), _FakeConnection(True), None),  # type: ignore[arg-type]
        }
        loop.run_until_complete(asyncio.gather(*(link.task for link in manager._links.values())))
    finally:
        loop.close()
    return manager


def test_only_live_links_are_reported_and_pro_comes_first() -> None:
    manager = _manager_with_links()

    assert manager.get_connected_serial_numbers() == [1, 2, 5]
    assert manager.get_connected_device_strings() == ["SN2 (P2 Pro)", "SN1 (P2)", "SN5 (P2)"]


def test_device_type_is_learned_from_connection_points() -> None:
    manager = _manager_with_links()
    manager._links[5].device_type = None

    point = NaneosDeviceDataPoint(
        unix_timestamp=1000,
        serial_number=5,
        connection_type=ConnectionType.CONNECTED,
        device_type=DeviceType.P2PRO,
        ldsa=1.0,
    )
    manager._queue_connection.put_nowait(point)
    asyncio.run(manager._connection_queue_routine())

    assert manager._links[5].device_type == DeviceType.P2PRO
    assert list(manager.get_data()[5]["ldsa"]) == [1.0]


def test_finished_tasks_are_forgotten() -> None:
    manager = _manager_with_links()  # every task has already finished

    manager._forget_finished_links()

    assert manager._links == {}

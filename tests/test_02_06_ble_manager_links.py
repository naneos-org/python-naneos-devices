"""Hardware-free tests for the link bookkeeping of PartectorBleManager."""

import asyncio
import time

from naneos.ble.partector.manager import BleLink, PartectorBleManager
from naneos.data_point import ConnectionType, DeviceType, NaneosDeviceDataPoint


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


class _FakeScanner:
    """A scanner whose hearing is set by the test."""

    def __init__(self, seconds_since_advertisement: float | None, silent_for: float) -> None:
        self.seconds_since_advertisement = seconds_since_advertisement
        self.silent_for = silent_for
        self.restarts: list[bool] = []

    async def restart(self, switch_mode: bool = False) -> None:
        self.restarts.append(switch_mode)
        self.silent_for = 0.0  # a new scan starts listening from zero


def _revive(manager: PartectorBleManager, link_down_for: float) -> None:
    manager._link_down_since = time.monotonic() - link_down_for
    asyncio.run(manager._revive_silent_scanner())


def test_a_deaf_scanner_is_restarted_while_a_link_waits() -> None:
    manager = _manager_with_links()  # links 3 and 4 are not connected
    scanner = _FakeScanner(seconds_since_advertisement=90.0, silent_for=90.0)
    manager._scanner = scanner  # type: ignore[assignment]

    _revive(manager, link_down_for=90.0)
    assert scanner.restarts == [False]

    # The next restart has to wait twice as long, and tries the other scan mode.
    scanner.seconds_since_advertisement, scanner.silent_for = 190.0, 100.0
    _revive(manager, link_down_for=190.0)
    assert scanner.restarts == [False]

    scanner.seconds_since_advertisement, scanner.silent_for = 215.0, 125.0
    _revive(manager, link_down_for=215.0)
    assert scanner.restarts == [False, True]


def test_a_scanner_that_hears_partectors_is_left_alone() -> None:
    manager = _manager_with_links()
    scanner = _FakeScanner(seconds_since_advertisement=2.0, silent_for=2.0)
    manager._scanner = scanner  # type: ignore[assignment]

    _revive(manager, link_down_for=500.0)  # e.g. a device that is too weak to connect

    assert scanner.restarts == []


def test_silence_is_normal_while_every_link_is_up() -> None:
    manager = _manager_with_links()
    for serial in (3, 4):
        manager._links[serial].connection = _FakeConnection(True)  # type: ignore[assignment]
    scanner = _FakeScanner(seconds_since_advertisement=3600.0, silent_for=3600.0)
    manager._scanner = scanner  # type: ignore[assignment]

    asyncio.run(manager._revive_silent_scanner())
    assert scanner.restarts == []

    # A link that drops after a long silence gets its minute to be heard first.
    manager._links[3].connection = _FakeConnection(False)  # type: ignore[assignment]
    asyncio.run(manager._revive_silent_scanner())
    assert scanner.restarts == []

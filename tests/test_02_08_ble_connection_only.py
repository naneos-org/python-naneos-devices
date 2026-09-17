"""Hardware-free tests for the connection-only BLE mode: allow-list, link cap, scanner setup."""

import asyncio

from bleak.backends.device import BLEDevice

from naneos.ble.partector.manager import BleLink, PartectorBleManager
from naneos.ble.partector.scanner import PartectorBleScanner


class _FakeScanner:
    def __init__(self, rssi: dict[str, int]) -> None:
        self._rssi = rssi

    def get_rssi(self, address: str) -> int | None:
        return self._rssi.get(address)

    def get_device(self, address: str) -> BLEDevice | None:
        return None


def _device(address: str) -> BLEDevice:
    return BLEDevice(address, "P2", None)


def _drain(manager: PartectorBleManager, seen: list[tuple[str, int]], rssi: dict[str, int]):
    """Feed advertisements into the scanner queue and run one manager drain."""

    async def run() -> None:
        manager._loop = asyncio.get_running_loop()
        manager._scanner = _FakeScanner(rssi)  # type: ignore[assignment]
        # The connection task would touch a real adapter; replace it by an idle task.
        manager._task_connection = lambda device, serial: asyncio.sleep(0)  # type: ignore[method-assign]
        before = set(manager._links)
        for address, serial in seen:
            manager._queue_scanner.put_nowait((_device(address), serial))
        await manager._scanner_queue_routine()
        # Only the tasks created in this drain belong to this loop.
        await asyncio.gather(
            *(link.task for sn, link in manager._links.items() if sn not in before)
        )

    asyncio.run(run())


def test_advertisements_only_create_links_never_data() -> None:
    manager = PartectorBleManager()

    _drain(manager, [("AA", 1), ("BB", 2)], {"AA": -60, "BB": -60})

    assert sorted(manager._links) == [1, 2]
    assert manager.get_data() == {}  # nothing is buffered from advertisements


def test_allow_list_restricts_links() -> None:
    manager = PartectorBleManager(serial_numbers=[2])

    _drain(manager, [("AA", 1), ("BB", 2), ("CC", 3)], {})

    assert list(manager._links) == [2]


def test_link_cap_counts_existing_links_including_retrying_ones() -> None:
    manager = PartectorBleManager(max_links=2)

    _drain(manager, [("AA", 1), ("BB", 2), ("CC", 3)], {})
    assert len(manager._links) == 2
    assert 3 not in manager._links

    manager._links.pop(1)  # a link went away
    _drain(manager, [("CC", 3)], {})
    assert sorted(manager._links) == [2, 3]


def test_weak_devices_are_skipped_but_unknown_rssi_is_allowed() -> None:
    manager = PartectorBleManager()

    _drain(manager, [("AA", 1), ("BB", 2)], {"AA": -86})  # BB has no reading yet

    assert list(manager._links) == [2]


def test_scanner_kwargs_passive_carries_the_bluez_filter() -> None:
    assert PartectorBleScanner.scanner_kwargs(passive=False) == {}

    kwargs = PartectorBleScanner.scanner_kwargs(passive=True)
    assert kwargs["scanning_mode"] == "passive"
    patterns = kwargs["bluez"]["or_patterns"]
    assert len(patterns) == 3
    assert patterns[0].content_of_pattern == b"X"  # the Partector protocol byte


def test_ble_link_reports_connected_only_with_a_live_client() -> None:
    class Client:
        is_connected = True

    loop = asyncio.new_event_loop()
    try:
        task = loop.create_task(asyncio.sleep(0))
        loop.run_until_complete(task)
    finally:
        loop.close()
    assert not BleLink(task).is_connected
    assert BleLink(task, Client()).is_connected  # type: ignore[arg-type]

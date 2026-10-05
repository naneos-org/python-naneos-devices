"""Hardware-free tests for what the tray menu says (no Qt needed)."""

import queue
from dataclasses import dataclass

from naneos.data_point import ConnectionType, DeviceType
from naneos.gui.model import (
    LastSeen,
    format_age,
    format_device_row,
    format_status,
    format_title,
    format_tooltip,
    sort_devices,
)


@dataclass
class FakeDevice:
    serial_number: int | None
    device_type: DeviceType | None
    connection_type: ConnectionType


@dataclass
class FakePoint:
    serial_number: int | None


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_format_age() -> None:
    assert format_age(None) == "–"
    assert format_age(0) == "0 s"
    assert format_age(1.9) == "1 s"
    assert format_age(59.9) == "59 s"
    assert format_age(60) == "1 min"
    assert format_age(3599) == "59 min"
    assert format_age(3600) == "1 h"
    assert format_age(7300) == "2 h"


def test_format_device_row_matches_the_menu_mock() -> None:
    usb_pro = FakeDevice(8764, DeviceType.P2PRO, ConnectionType.SERIAL)
    ble_p2 = FakeDevice(8123, DeviceType.P2, ConnectionType.CONNECTED)

    assert format_device_row(usb_pro, 1.2) == "P2 Pro  SN8764  USB  1 s"
    assert format_device_row(ble_p2, 2.7) == "P2      SN8123  BLE  2 s"


def test_format_device_row_for_a_device_that_has_not_told_itself_yet() -> None:
    unknown = FakeDevice(None, None, ConnectionType.SERIAL)
    assert format_device_row(unknown, None) == "?       SN?  USB  –"


def test_devices_are_sorted_by_serial_number_and_unknown_ones_go_last() -> None:
    a = FakeDevice(8764, DeviceType.P2PRO, ConnectionType.SERIAL)
    b = FakeDevice(8123, DeviceType.P2, ConnectionType.CONNECTED)
    c = FakeDevice(None, None, ConnectionType.SERIAL)
    assert sort_devices([a, c, b]) == [b, a, c]


def test_last_seen_measures_the_time_since_the_last_point() -> None:
    clock = FakeClock()
    seen = LastSeen(clock)
    assert seen.age(8617) is None

    seen.note(8617)
    clock.now += 2.5
    assert seen.age(8617) == 2.5
    assert seen.age(9999) is None

    seen.note(8617)
    assert seen.age(8617) == 0.0


def test_last_seen_ignores_points_without_a_serial_number() -> None:
    seen = LastSeen(FakeClock())
    seen.note(None)
    assert seen.age(None) is None


def test_last_seen_drains_the_live_queue() -> None:
    clock = FakeClock()
    seen = LastSeen(clock)
    points: queue.Queue[FakePoint] = queue.Queue()
    for serial in (8617, 8764, 8617):
        points.put(FakePoint(serial))

    assert seen.drain(points) == 3
    assert points.empty()
    assert seen.age(8617) == 0.0
    assert seen.age(8764) == 0.0
    assert seen.drain(points) == 0


def test_last_seen_forgets_devices_that_are_gone() -> None:
    clock = FakeClock()
    seen = LastSeen(clock)
    seen.note(1)
    seen.note(2)

    seen.forget_except([2, None])

    assert seen.age(1) is None
    assert seen.age(2) == 0.0


def test_status_line() -> None:
    assert format_status(True, 0, False) == "Upload: on · 0 pending"
    assert format_status(True, 12, False) == "Upload: on · 12 pending"
    assert format_status(False, 12, False) == "Upload: off"
    assert format_status(True, 0, True) == "Upload: on · 0 pending · diagnostics"


def test_title_and_tooltip() -> None:
    assert format_title("2.1.0") == "naneos devices 2.1.0"
    assert format_tooltip("2.1.0", 0) == "naneos devices 2.1.0 – 0 devices"
    assert format_tooltip("2.1.0", 1) == "naneos devices 2.1.0 – 1 device"
    assert format_tooltip("2.1.0", 3) == "naneos devices 2.1.0 – 3 devices"

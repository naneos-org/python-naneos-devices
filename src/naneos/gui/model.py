"""What the tray menu says about the devices, without Qt.

The tray asks the manager for the connected devices and remembers when each of
them last delivered a data point, so the menu can show

    P2 Pro  SN8764  USB  1 s
    P2      SN8123  BLE  2 s
"""

import queue
import time
from collections.abc import Callable, Iterable
from typing import Protocol, TypeVar

from naneos.data_point import ConnectionType, DeviceType

TYPE_NAMES = {DeviceType.P2: "P2", DeviceType.P1: "P1", DeviceType.P2PRO: "P2 Pro"}
CONNECTION_NAMES = {ConnectionType.SERIAL: "USB", ConnectionType.CONNECTED: "BLE"}

_TYPE_WIDTH = max(len(name) for name in TYPE_NAMES.values())

# One drain never takes more than this many points, so a fast producer cannot
# keep the GUI thread busy for ever.
_MAX_DRAIN = 20_000


class DeviceLike(Protocol):
    """The part of PartectorDevice the menu needs."""

    @property
    def serial_number(self) -> int | None: ...

    @property
    def device_type(self) -> DeviceType | None: ...

    @property
    def connection_type(self) -> ConnectionType: ...


class PointLike(Protocol):
    @property
    def serial_number(self) -> int | None: ...


D = TypeVar("D", bound=DeviceLike)
P = TypeVar("P", bound=PointLike)


class LastSeen:
    """When each serial number last delivered a data point (monotonic clock).

    The arrival time is used, not the timestamp in the data point, so a device
    with a wrong clock still shows how long it has been silent.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._seen: dict[int, float] = {}

    def note(self, serial_number: int | None) -> None:
        if serial_number is not None:
            self._seen[serial_number] = self._clock()

    def drain(self, points: "queue.Queue[P]") -> int:
        """Take every waiting point off the live queue. Returns how many."""
        taken = 0
        while taken < _MAX_DRAIN:
            try:
                point = points.get_nowait()
            except queue.Empty:
                break
            self.note(point.serial_number)
            taken += 1
        return taken

    def age(self, serial_number: int | None) -> float | None:
        """Seconds since the last point, None if there was none yet."""
        if serial_number is None or serial_number not in self._seen:
            return None
        return max(0.0, self._clock() - self._seen[serial_number])

    def forget_except(self, serial_numbers: Iterable[int | None]) -> None:
        """Drop devices that are gone, so a device that comes back starts at "–"."""
        keep = {sn for sn in serial_numbers if sn is not None}
        self._seen = {sn: at for sn, at in self._seen.items() if sn in keep}


def format_age(age_seconds: float | None) -> str:
    if age_seconds is None:
        return "–"
    if age_seconds < 60:
        return f"{int(age_seconds)} s"
    if age_seconds < 3600:
        return f"{int(age_seconds // 60)} min"
    return f"{int(age_seconds // 3600)} h"


def format_device_row(device: DeviceLike, age_seconds: float | None) -> str:
    type_name = TYPE_NAMES.get(device.device_type, "?") if device.device_type is not None else "?"
    serial = f"SN{device.serial_number}" if device.serial_number is not None else "SN?"
    connection = CONNECTION_NAMES.get(device.connection_type, "?")
    return f"{type_name:<{_TYPE_WIDTH}}  {serial}  {connection}  {format_age(age_seconds)}"


def sort_devices(devices: Iterable[D]) -> list[D]:
    """By serial number; a device that has not told its number yet goes last."""
    return sorted(
        devices,
        key=lambda d: (d.serial_number is None, d.serial_number if d.serial_number else 0),
    )


def format_title(version: str) -> str:
    return f"naneos devices {version}"


def format_status(upload_active: bool, pending_count: int, diagnostics_running: bool) -> str:
    text = f"Upload: on · {pending_count} pending" if upload_active else "Upload: off"
    return f"{text} · diagnostics" if diagnostics_running else text


def format_tooltip(version: str, device_count: int) -> str:
    noun = "device" if device_count == 1 else "devices"
    return f"{format_title(version)} – {device_count} {noun}"

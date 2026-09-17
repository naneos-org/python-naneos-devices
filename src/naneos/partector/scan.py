"""Find Partectors on the serial ports of this machine."""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from naneos.data_point import DeviceType
from naneos.logger import get_naneos_logger
from naneos.partector.serial_transport import SerialTransport
from naneos.serial_utils import list_serial_ports

logger = get_naneos_logger(__name__)

# Key used for each family in the dict returned by scan_for_serial_partectors().
DEVICE_KIND_NAMES: dict[DeviceType, str] = {
    DeviceType.P1: "P1",
    DeviceType.P2: "P2",
    DeviceType.P2PRO: "P2pro",
}

# Serial numbers below this belong to the Partector 1 family.
_P1_MAX_SERIAL_NUMBER = 1000
# Firmware from which a P2 answers the "name?" query that tells P2 and P2 Pro apart.
_FW_WITH_NAME_QUERY = 310

# Answers to the "name?" query.
_DEVICE_NAMES: dict[str, DeviceType] = {"P2": DeviceType.P2, "P2pro": DeviceType.P2PRO}

_ANSWER_TIMEOUT_SECONDS = 0.25
_ASK_RETRIES = 3


@dataclass(frozen=True)
class FoundDevice:
    serial_number: int
    port: str
    kind: DeviceType
    firmware: int


def scan_serial_ports(ports_exclude: list[str] | None = None) -> list[FoundDevice]:
    """Identify the Partector behind every candidate serial port, in parallel."""
    ports = list_serial_ports(ports_exclude=ports_exclude or [])
    if not ports:
        return []

    with ThreadPoolExecutor(max_workers=len(ports)) as pool:
        found = [device for device in pool.map(_scan_port, ports) if device is not None]

    logger.debug(f"Found devices: {found}")
    return found


def scan_for_serial_partectors(ports_exclude: list[str] | None = None) -> dict[str, dict[int, str]]:
    """Found devices grouped by family: {"P1": {sn: port}, "P2": {...}, "P2pro": {...}}."""
    grouped: dict[str, dict[int, str]] = {name: {} for name in DEVICE_KIND_NAMES.values()}
    for device in scan_serial_ports(ports_exclude):
        grouped[DEVICE_KIND_NAMES[device.kind]][device.serial_number] = device.port
    return grouped


def scan_for_serial_partector(
    serial_number: int, kind: DeviceType | str | None = None
) -> str | None:
    """Port of the device with this serial number, or None if it is not plugged in.

    kind restricts the search to one family; it accepts a DeviceType or one of
    the names "P1", "P2", "P2pro".
    """
    if isinstance(kind, str):
        by_name = {name: device_type for device_type, name in DEVICE_KIND_NAMES.items()}
        kind = by_name.get(kind)

    for device in scan_serial_ports():
        if device.serial_number == serial_number and (kind is None or device.kind == kind):
            return device.port

    return None


def _scan_port(port: str) -> FoundDevice | None:
    """Identify the device behind a port without starting a reader thread."""
    transport = SerialTransport(port)
    try:
        transport.open()
        transport.write("X0000!")  # silence the device while it is identified
        time.sleep(10e-3)
        transport.discard_input()

        serial_number = _ask_serial_number(transport)
        if serial_number is None:
            return None  # every port is scanned, most have no Partector behind them

        firmware = _ask_int(transport, "f?") or 0
        kind = _classify(transport, serial_number, firmware)
        return FoundDevice(serial_number, port, kind, firmware)
    except ConnectionError as e:
        logger.debug(f"Scanning {port} failed: {e}")
        return None
    finally:
        transport.close()


def _classify(transport: SerialTransport, serial_number: int, firmware: int) -> DeviceType:
    if serial_number < _P1_MAX_SERIAL_NUMBER:
        return DeviceType.P1
    if firmware < _FW_WITH_NAME_QUERY:
        return DeviceType.P2

    # Only a known name counts: a late or cut off line must not turn a P2 Pro
    # into a P2, which would then be read with the wrong line layout.
    for _ in range(_ASK_RETRIES):
        name = _ask(transport, "name?")
        if name in _DEVICE_NAMES:
            return _DEVICE_NAMES[name]
    logger.warning(f"SN{serial_number} did not tell its name, treating it as a P2.")
    return DeviceType.P2


def _ask(transport: SerialTransport, command: str) -> str | None:
    """The single field answer to a command, or None. The device must be silenced."""
    transport.write(command)
    deadline = time.monotonic() + _ANSWER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        line = transport.readline()
        # A line with tabs is a verbose line that was still on its way.
        if line and "\t" not in line:
            return line
    return None


def _ask_int(transport: SerialTransport, command: str) -> int | None:
    for _ in range(_ASK_RETRIES):
        answer = _ask(transport, command)
        try:
            if answer is not None:
                return int(answer)
        except ValueError:
            pass
    return None


def _ask_serial_number(transport: SerialTransport) -> int | None:
    """The serial number, once three reads in a row agree on it."""
    for _ in range(3):
        numbers = [_ask_int(transport, "N?") for _ in range(3)]
        if numbers[0] is not None and numbers[0] == numbers[1] == numbers[2]:
            return numbers[0]
        if numbers == [None, None, None]:
            return None
    return None

"""Find Partectors on the serial ports of this machine."""

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import serial
from serial.tools import list_ports

from naneos.data_point import DeviceType
from naneos.logger import get_naneos_logger
from naneos.usb.transport import SerialTransport

logger = get_naneos_logger(__name__)

# Serial numbers below this belong to the Partector 1 family.
_P1_MAX_SERIAL_NUMBER = 1000
# Firmware from which a P2 answers the "name?" query that tells P2 and P2 Pro apart.
_FW_WITH_NAME_QUERY = 310

# USB identifiers of the Partector serial interface.
_PARTECTOR_VID = 65535
_PARTECTOR_PID = 5
# A P2 streaming at 100 Hz can make the open() on Windows fail transiently,
# so a port is only given up after this many immediate retries.
_PORT_OPEN_RETRIES = 100

# A P2 Pro stops answering for up to ~0.7 s once per size distribution cycle
# (measured on FW420). A shorter timeout runs out of retries during that pause
# and the late answers then arrive one question behind, which is how a P2 Pro
# gets taken for a P2 (and switched to the plain P2 output by "X0001!").
_ANSWER_TIMEOUT_SECONDS = 1.0
_ASK_RETRIES = 3


@dataclass(frozen=True)
class FoundDevice:
    serial_number: int
    port: str
    kind: DeviceType
    firmware: int | None  # None: the device did not answer f?


def scan_serial_ports(ports_exclude: list[str] | None = None) -> list[FoundDevice]:
    """Identify the Partector behind every candidate serial port, in parallel."""
    ports = list_serial_ports(ports_exclude=ports_exclude or [])
    if not ports:
        return []

    with ThreadPoolExecutor(max_workers=len(ports)) as pool:
        found = [device for device in pool.map(_scan_port, ports) if device is not None]

    logger.debug(f"Found devices: {found}")
    return found


def scan_for_serial_partector(serial_number: int, kind: DeviceType | None = None) -> str | None:
    """Port of the device with this serial number, or None if it is not plugged in.

    kind restricts the search to one device family.
    """
    for device in scan_serial_ports():
        if device.serial_number == serial_number and (kind is None or device.kind == kind):
            return device.port

    return None


def list_serial_ports(ports_exclude: list[str] | None = None) -> list[str]:
    """Serial ports that look like a Partector and can be opened, excluding ports_exclude."""
    exclude = ports_exclude or []
    candidates = [
        port.device
        for port in list_ports.comports()
        if port.device not in exclude
        and (
            (port.pid == _PARTECTOR_PID and port.vid == _PARTECTOR_VID)
            or (port.serial_number and "dosemet" in port.serial_number.lower())
        )
    ]
    return [port for port in candidates if _can_open(port)]


def _can_open(port: str) -> bool:
    for _ in range(_PORT_OPEN_RETRIES):
        try:
            with serial.Serial(port) as ser:
                ser.write(b"X0000!")
            return True
        except (OSError, serial.SerialException):
            pass
    return False


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

        firmware = _ask_int(transport, "f?")
        kind = _classify(transport, serial_number, firmware)
        return FoundDevice(serial_number, port, kind, firmware)
    except ConnectionError as e:
        logger.debug(f"Scanning {port} failed: {e}")
        return None
    finally:
        transport.close()


def _classify(transport: SerialTransport, serial_number: int, firmware: int | None) -> DeviceType:
    if serial_number < _P1_MAX_SERIAL_NUMBER:
        return DeviceType.P1
    # An unknown firmware (no answer to "f?") is not taken for an old one: the
    # name decides, so that a P2 Pro is never silently handled as a P2.
    if firmware is not None and firmware < _FW_WITH_NAME_QUERY:
        return DeviceType.P2

    # Only a known name counts: a late or cut off line must not turn a P2 Pro
    # into a P2, which would then be read with the wrong line layout.
    for _ in range(_ASK_RETRIES):
        name = _ask(transport, "name?", lambda answer: DeviceType.from_name(answer) is not None)
        kind = DeviceType.from_name(name) if name is not None else None
        if kind is not None:
            return kind
    logger.warning(f"SN{serial_number} did not tell its name, treating it as a P2.")
    return DeviceType.P2


def _ask(
    transport: SerialTransport, command: str, accept: Callable[[str], bool] = lambda _: True
) -> str | None:
    """The single field answer to a command, or None. The device must be silenced.

    Lines that accept() rejects are skipped: they are late answers to an
    earlier question or verbose lines that were still on their way.
    """
    transport.discard_input()  # the late answer to an earlier question
    transport.write(command)
    deadline = time.monotonic() + _ANSWER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        line = transport.readline()
        if line and "\t" not in line and accept(line):
            return line
    return None


def _ask_int(transport: SerialTransport, command: str) -> int | None:
    for _ in range(_ASK_RETRIES):
        answer = _ask(transport, command, _is_int)
        if answer is not None:
            return int(answer)
    return None


def _is_int(line: str) -> bool:
    try:
        int(line)
    except ValueError:
        return False
    return True


def _ask_serial_number(transport: SerialTransport) -> int | None:
    """The serial number, once three reads in a row agree on it."""
    for _ in range(3):
        numbers = [_ask(transport, "N?", _is_int) for _ in range(3)]
        if numbers[0] is not None and numbers[0] == numbers[1] == numbers[2]:
            return int(numbers[0])
        if numbers == [None, None, None]:
            return None
    return None

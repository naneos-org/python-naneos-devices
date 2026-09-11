"""Find Partectors on the serial ports of this machine."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from naneos.data_point import DeviceType
from naneos.logger import get_naneos_logger
from naneos.partector.blueprints._partector_blueprint import PartectorBlueprint
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


@dataclass(frozen=True)
class FoundDevice:
    serial_number: int
    port: str
    kind: DeviceType
    firmware: int


class ScanPartector(PartectorBlueprint):
    """Minimal device used to identify what is behind a port. Never streams data."""

    def _init_print_connection_info(self) -> None:
        pass

    def _init_serial_data_structure(self) -> None:
        """Not used by the scan partector, but mandatory in the partector blueprint."""

    def _serial_wrapper(self, func) -> Any | None:
        """Like the blueprint, but raises instead of logging: a port without a
        Partector behind it must not produce warnings."""
        if not self._connected:
            return None

        excep = "Was not able to fetch the serial number!"

        for _ in range(self.SERIAL_RETRIES):
            try:
                return func()
            except Exception as e:
                excep = f"SN{self._sn} Exception occurred during user function call: {e}"

        raise Exception(excep)

    def _init_get_device_info(self) -> None:
        try:
            if self._sn is None:
                self._sn = self._get_serial_number_secure()
            self._fw = self.get_firmware_version()
            logger.debug(f"Connected to SN{self._sn} on {self._port}")
        except Exception:
            # Every port is scanned, so most of them simply have no Partector.
            pass

    def _set_verbose_freq(self, freq: int = 0) -> None:
        """Only ever used to silence the device while it is identified."""
        self._write_line("X0000!")


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
    partector: ScanPartector | None = None
    try:
        partector = ScanPartector(port=port)
        if partector._sn is None:
            return None

        kind = _classify(partector)
        return FoundDevice(partector._sn, port, kind, partector._fw)
    except Exception as e:
        logger.debug(f"Scanning {port} failed: {e}")
        return None
    finally:
        if partector is not None:
            partector.close(blocking=True)


def _classify(partector: ScanPartector) -> DeviceType:
    assert partector._sn is not None
    if partector._sn < _P1_MAX_SERIAL_NUMBER:
        return DeviceType.P1
    if partector._fw < _FW_WITH_NAME_QUERY:
        return DeviceType.P2

    name = partector.write_line("name?")[1]
    if name == "P2pro":
        return DeviceType.P2PRO
    return DeviceType.P2

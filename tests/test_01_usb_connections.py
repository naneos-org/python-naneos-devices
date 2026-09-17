import time
import warnings

import pytest

from naneos.usb import PartectorSerialManager
from naneos.usb.partector.manager import DEVICE_CLASSES
from naneos.usb.partector.scan import list_serial_ports, scan_serial_ports

pytestmark = pytest.mark.hardware  # needs a Partector on USB or BLE


def test_list_serial_ports():
    """
    Test the list_serial_ports function to ensure it returns a list of connected USB devices.
    """
    # Call the function to get the list of serial ports with partectors connected
    serial_ports = list_serial_ports()

    # Check if the result is a list
    assert isinstance(serial_ports, list), "The result should be a list."
    # Check if the list is not empty (assuming there are connected devices)
    assert len(serial_ports) > 0, "There is no connected USB partector device."


def test_connection_partectors() -> None:
    """Every device found must connect by serial number five times in a row."""
    found = scan_serial_ports()
    assert len(found) > 0, "There is no connected USB partector device."

    for device in found:
        for _ in range(5):
            partector = DEVICE_CLASSES[device.kind](serial_number=device.serial_number)
            assert partector.firmware_version == device.firmware, (
                f"scan found {device}, the connected device says FW{partector.firmware_version}"
            )
            partector.close(reset_device=False)

    for kind in set(DEVICE_CLASSES) - {device.kind for device in found}:
        warnings.warn(f"There is no {kind.name} connected (USB).", UserWarning, stacklevel=2)


def test_serial_manager():
    """Data must arrive from every device the scan found.

    Connecting takes a few seconds and the gain test then holds the output
    back for at least 10 s, so poll with a deadline instead of a fixed sleep.
    """
    expected = len(scan_for_serial_partectors_flat())
    assert expected > 0, "There is no connected USB partector device."

    manager = PartectorSerialManager()
    manager.start()

    data: dict = {}
    deadline = time.time() + 60
    try:
        while time.time() < deadline and len(data) < expected:
            time.sleep(1)
            for sn, df in manager.get_data().items():
                data[sn] = df
    finally:
        manager.stop()
        manager.join()

    assert isinstance(data, dict), "Data should be a dictionary."
    assert len(data) == expected, f"Got data from {sorted(data)} only."

    print("Collected data:")
    print()
    for sn, df in data.items():
        print(f"SN: {sn}")
        print(df)
        print("-" * 40)
        print()


def scan_for_serial_partectors_flat() -> list[int]:
    return [device.serial_number for device in scan_serial_ports()]

"""A P2 Pro left in the plain P2 mode is put back into size distribution mode by its BLE link.

Needs a P2 Pro on USB that is also in BLE range. The test puts it into the plain mode over USB,
lets the BLE manager connect, and waits for the first size distribution point. The device is
left in size distribution mode, its default.
"""

import time

import pytest

from naneos.ble.partector.manager import PartectorBleManager
from naneos.data_point import DeviceType, NaneosDeviceDataPoint
from naneos.usb.partector.manager import DEVICE_CLASSES
from naneos.usb.partector.scan import scan_serial_ports

pytestmark = pytest.mark.hardware  # a P2 Pro on USB, reachable over BLE

LINK_SECONDS = 60
SIZE_DISTRIBUTION_SECONDS = (
    60  # the longest cycle is ~21 s, and the switch takes a few seconds more
)


@pytest.mark.timeout(LINK_SECONDS + SIZE_DISTRIBUTION_SECONDS + 60)
def test_ble_puts_a_p2_pro_in_the_plain_mode_back_into_size_distribution_mode() -> None:
    found = next((d for d in scan_serial_ports() if d.kind == DeviceType.P2PRO), None)
    if found is None:
        pytest.skip("needs a P2 Pro on USB")
    serial = found.serial_number

    usb = DEVICE_CLASSES[found.kind](found.serial_number, found.port, sample_rate_hz=10)
    time.sleep(2)
    usb.close()  # the output goes off, the plain mode stays

    points: list[NaneosDeviceDataPoint] = []
    manager = PartectorBleManager([serial], 1, points.append)
    manager.start()
    try:
        deadline = time.monotonic() + LINK_SECONDS
        while time.monotonic() < deadline and not manager.get_connected_serial_numbers():
            time.sleep(0.5)
        if not manager.get_connected_serial_numbers():
            pytest.skip(f"SN{serial} is not reachable over BLE")

        deadline = time.monotonic() + SIZE_DISTRIBUTION_SECONDS
        while time.monotonic() < deadline and not any(
            p.particle_number_10nm is not None for p in points if p.serial_number == serial
        ):
            time.sleep(1)
    finally:
        manager.stop()
        manager.join(30)

    assert any(p.particle_number_10nm is not None for p in points if p.serial_number == serial)

import warnings

from naneos.partector import (
    Partector1,
    Partector2,
    Partector2Pro,
    scan_for_serial_partectors,
)
from naneos.serial_utils import list_serial_ports


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
    """Test if the serial connection is working 10 times."""
    partectors = scan_for_serial_partectors()
    assert isinstance(partectors, dict), "The result should be a list."
    assert len(partectors) > 0, "There is no connected USB partector device."

    p1 = partectors["P1"]
    p2 = partectors["P2"]
    p2_pro = partectors["P2pro"]

    if len(p1) > 0:
        serial_number = next(iter(p1.keys()))
        for _ in range(5):
            p1 = Partector1(serial_number=serial_number)
            p1.close(verbose_reset=False)
    else:
        warnings.warn("There is no P1 connected (USB).", UserWarning)

    if len(p2) > 0:
        serial_number = next(iter(p2.keys()))
        for _ in range(5):
            p2 = Partector2(serial_number=serial_number)
            p2.close(verbose_reset=False)
    else:
        warnings.warn("There is no P2 connected (USB).", UserWarning)

    if len(p2_pro) > 0:
        serial_number = next(iter(p2_pro.keys()))
        for _ in range(5):
            p2_pro = Partector2Pro(serial_number=serial_number)
            p2_pro.close(verbose_reset=False)
    else:
        warnings.warn("There is no P2pro connected (USB).", UserWarning)

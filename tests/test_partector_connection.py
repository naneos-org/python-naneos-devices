import time

from naneos.partector import Partector2Pro, scan_for_serial_partectors


def test_partector2_pro() -> None:
    """Test if the serial connection is working 10 times."""
    partectors = scan_for_serial_partectors()
    p2_pro = partectors["P2pro"]

    assert p2_pro, "No Partector found!"

    serial_number = next(iter(p2_pro.keys()))

    for _ in range(10):
        p2 = Partector2Pro(serial_number=serial_number)
        time.sleep(0.2)
        p2.close()
        time.sleep(0.2)

from naneos.partector2_ble import Partector2Ble
import time


def test_bluetooth_connection():
    p2 = Partector2Ble()
    time.sleep(2)
    assert p2.get_and_clear_results() != {}
    p2.stop_scanning()

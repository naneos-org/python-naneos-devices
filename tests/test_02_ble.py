import time

from naneos.partector_ble.partector_ble_manager import PartectorBleManager

# TODO: it would be nice to have a test that works without access to the bluetooth peripherals


def test_connection_to_partector():
    with PartectorBleManager() as manager:
        time.sleep(5)  # Let it run for a while
        # TODO: add data extraction and validation here in the future

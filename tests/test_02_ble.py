import time

from naneos.partector_ble.partector_ble import PartectorBle


def test_connection_to_partector():
    partector_ble = PartectorBle(serial_numbers=[8112])
    partector_ble.start()

    time.sleep(10)

    upload_list = partector_ble.get_upload_list()

    partector_ble.event.set()
    partector_ble.join()

    assert isinstance(upload_list, list), "The result should be a list."
    assert len(upload_list) > 0, "There was no data received."

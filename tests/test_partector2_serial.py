import time

from naneos.partector2 import Partector2, scan_for_serial_partector2

# make sure a physical partector2 is connected


def test_port_scanning():
    ports = scan_for_serial_partector2()
    assert len(ports) > 0
    assert isinstance(ports, dict)
    assert isinstance(list(ports.keys())[0], int)
    assert isinstance(list(ports.values())[0], str)


def test_partector_data_list():
    p2 = _find_and_connect_partector2(2)

    time.sleep(2)

    data = p2.get_data_list()

    assert 10 < len(data) < 30

    p2.close(blocking=True)


def test_partector_pandas():
    p2 = _find_and_connect_partector2(3)

    time.sleep(2)

    data = p2.get_data_pandas()

    assert 100 < len(data) < 300

    p2.close(blocking=True)


def test_partector_upload_format():
    p2 = _find_and_connect_partector2(2)
    time.sleep(1)

    data = p2.get_lambda_upload_list()
    assert 5 < len(data) < 15
    assert type(data) == list
    assert type(data[0]) == dict

    p2.close(blocking=True)


def test_partector_freq_change():
    p2 = _find_and_connect_partector2(0)
    time.sleep(2)

    data = p2.get_data_pandas()
    assert len(data) == 0

    p2.set_verbose_freq(1)
    time.sleep(2)
    data = p2.get_data_pandas()
    assert 1 <= len(data) <= 3

    p2.set_verbose_freq(2)
    time.sleep(2)
    data = p2.get_data_pandas()
    assert 10 < len(data) < 30

    p2.set_verbose_freq(3)
    time.sleep(2)
    data = p2.get_data_pandas()
    assert 100 < len(data) < 300

    p2.close(blocking=True)


def _find_and_connect_partector2(freq: int = 0):
    scan = scan_for_serial_partector2()
    sn = list(scan.keys())[0]
    port = list(scan.values())[0]

    p2 = Partector2(port, verb_freq=freq)
    assert p2._serial_number == sn

    return p2

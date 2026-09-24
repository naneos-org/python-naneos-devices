"""Hardware-free tests for PartectorSerialManager's data hand-over."""

import pytest

from naneos.data_point import ConnectionType, DeviceType, NaneosDeviceDataPoint
from naneos.usb.partector import manager as manager_module
from naneos.usb.partector.device import Partector1, Partector2, Partector2Pro
from naneos.usb.partector.manager import PartectorSerialManager
from naneos.usb.partector.scan import FoundDevice


class _FakeDevice:
    def __init__(
        self,
        serial_number: int,
        batches: list[list[NaneosDeviceDataPoint]],
        kind: DeviceType = DeviceType.P2,
    ) -> None:
        self.serial_number = serial_number
        self._batches = batches
        self.device_type = kind
        self.is_connected = True
        self.is_settling = False

    def get_data(self) -> list[NaneosDeviceDataPoint]:
        return self._batches.pop(0) if self._batches else []


def _point(serial_number: int, ts: int) -> NaneosDeviceDataPoint:
    return NaneosDeviceDataPoint(
        unix_timestamp=ts,
        serial_number=serial_number,
        connection_type=ConnectionType.SERIAL,
        ldsa=1.0,
    )


def test_get_data_returns_what_the_loop_fetched_and_clears_it() -> None:
    manager = PartectorSerialManager()
    manager._devices["/dev/fake"] = _FakeDevice(  # type: ignore[assignment]
        11, [[_point(11, 1000), _point(11, 2000)], [_point(11, 3000)]]
    )

    assert manager.get_data() == {}  # nothing fetched yet

    manager._fetch_data()
    manager._fetch_data()
    data = manager.get_data()

    assert list(data) == [11]
    assert list(data[11].index) == [1000, 2000, 3000]
    assert manager.get_data() == {}  # handed over, buffer is empty again


def test_fetch_collects_from_every_device_and_reports_them() -> None:
    manager = PartectorSerialManager()
    manager._devices["/dev/c"] = _FakeDevice(3, [[_point(3, 10)]], DeviceType.P2PRO)  # type: ignore[assignment]
    manager._devices["/dev/a"] = _FakeDevice(1, [[_point(1, 10)]], DeviceType.P1)  # type: ignore[assignment]
    manager._devices["/dev/b"] = _FakeDevice(2, [[_point(2, 10)]], DeviceType.P2)  # type: ignore[assignment]

    manager._fetch_data()

    assert sorted(manager.get_data()) == [1, 2, 3]
    assert manager.get_connected_serial_numbers() == [3, 1, 2]
    assert [device.serial_number for device in manager.get_devices()] == [3, 1, 2]
    assert manager.get_settling_serial_numbers() == []


def test_sample_rate_setting_is_applied_to_every_device_by_the_loop() -> None:
    manager = PartectorSerialManager(sample_rate_hz=10)
    assert manager.sample_rate_hz == 10

    rates: list[tuple[int, int | None]] = []
    for serial_number in (1, 2):
        device = _FakeDevice(serial_number, [])
        device.set_sample_rate = lambda hz, sn=serial_number: rates.append((sn, hz))  # type: ignore[attr-defined]
        manager._devices[f"/dev/{serial_number}"] = device  # type: ignore[assignment]

    manager._apply_sample_rate()
    assert rates == []  # nothing changed since the devices connected with the setting

    manager.sample_rate_hz = None
    manager._apply_sample_rate()
    assert rates == [(1, None), (2, None)]

    with pytest.raises(ValueError):
        manager.sample_rate_hz = 2
    with pytest.raises(ValueError):
        PartectorSerialManager(sample_rate_hz=5)


def test_connect_builds_the_class_of_the_kind_and_only_the_p2_family_gets_the_diagnostics(
    monkeypatch,
) -> None:
    built: list[tuple[str, dict]] = []

    class _Records:
        def __init__(self, **kwargs) -> None:  # no port, no thread: only note the call
            built.append((type(self).__name__, kwargs))

    class RecordedP1(_Records, Partector1): ...

    class RecordedP2(_Records, Partector2): ...

    class RecordedPro(_Records, Partector2Pro): ...

    monkeypatch.setattr(
        manager_module,
        "DEVICE_CLASSES",
        {DeviceType.P1: RecordedP1, DeviceType.P2: RecordedP2, DeviceType.P2PRO: RecordedPro},
    )
    manager = PartectorSerialManager(gain_test_active=False, sample_rate_hz=10)

    for kind in (DeviceType.P1, DeviceType.P2, DeviceType.P2PRO):
        manager._connect(FoundDevice(1, "/dev/x", kind, 422))

    assert [name for name, _ in built] == ["RecordedP1", "RecordedP2", "RecordedPro"]
    p1, p2, pro = (kwargs for _, kwargs in built)
    assert p1 == {"port": "/dev/x", "sample_rate_hz": 10, "point_listener": None}
    for kwargs in (p2, pro):
        assert kwargs["gain_test_active"] is False
        assert kwargs["output_pulse_diagnostics"] is True
        assert kwargs["sample_rate_hz"] == 10


def test_the_valid_manager_rates_are_the_rates_of_a_device_without_off() -> None:
    check = PartectorSerialManager.check_sample_rate
    assert [check(hz) for hz in (None, 1, 10, 100)] == [None, 1, 10, 100]
    for bad in (0, 5, 1000):  # 0 switches one device off; a manager always reads
        with pytest.raises(ValueError, match=r"\[1, 10, 100\]"):
            check(bad)

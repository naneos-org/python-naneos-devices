"""Hardware-free tests for the serial devices, run against a fake transport."""

import copy
import time

import pytest
from fake_transport import FakeTransport

from naneos.data_point import ConnectionType, DeviceType
from naneos.device import PartectorDevice
from naneos.usb.partector import layouts as ds
from naneos.usb.partector.device import Partector1, Partector2, Partector2Pro


def _wait_for(condition, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def _p2(**kwargs) -> tuple[Partector2, FakeTransport]:
    transport = FakeTransport(firmware=kwargs.pop("firmware", 422))
    kwargs.setdefault("gain_test_active", False)
    kwargs.setdefault("output_pulse_diagnostics", False)
    return Partector2(transport=transport, **kwargs), transport  # type: ignore[arg-type]


def _pro(**kwargs) -> tuple[Partector2Pro, FakeTransport]:
    transport = FakeTransport(serial_number=8764, firmware=424, name="P2pro")
    kwargs.setdefault("gain_test_active", False)
    kwargs.setdefault("output_pulse_diagnostics", False)
    return Partector2Pro(transport=transport, **kwargs), transport  # type: ignore[arg-type]


def test_connect_reads_the_device_info_and_starts_the_output() -> None:
    device, transport = _p2()
    try:
        assert isinstance(device, PartectorDevice)
        assert device.serial_number == 8617
        assert device.firmware_version == 422
        assert device.integration_time_seconds == 4
        assert device.device_type == DeviceType.P2
        assert device.connection_type == ConnectionType.SERIAL
        assert device.is_connected
        assert device.sample_rate_hz == 1
        assert transport.written[0] == "X0000!"  # silenced before it is asked anything
        assert transport.written[-1] == "X0001!"
    finally:
        device.close()


def test_connect_fails_if_nothing_answers_or_the_serial_number_is_wrong() -> None:
    silent = FakeTransport()
    silent.mute = True
    with pytest.raises(ConnectionError):
        Partector2(transport=silent)  # type: ignore[arg-type]
    assert not silent.is_open

    with pytest.raises(ConnectionError, match="not SN1"):
        Partector2(serial_number=1, transport=FakeTransport())  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        Partector2()


def test_sample_rate_is_given_in_hz() -> None:
    device, transport = _p2(sample_rate_hz=0)
    try:
        for hz, command in ((1, "X0001!"), (10, "X0002!"), (100, "X0003!"), (0, "X0000!")):
            device.set_sample_rate(hz)
            assert transport.written[-1] == command
            assert device.sample_rate_hz == hz

        with pytest.raises(ValueError):
            device.set_sample_rate(2)  # the old mode code for 10 Hz
    finally:
        device.close()


def test_query_returns_the_answer_fields_and_write_expects_none() -> None:
    device, transport = _p2()
    try:
        transport.answers["custom?"] = "a\tb"
        assert device.query("custom?") == ["a", "b"]
        assert device.query("name?") == ["P2"]

        device.write("A0002!")
        assert transport.written[-1] == "A0002!"

        with pytest.raises(TimeoutError):
            device.query("unknown?", timeout=0.05)
    finally:
        device.close()


def test_a_stale_answer_is_not_taken_for_the_next_one() -> None:
    device, transport = _p2()
    try:
        device.write("name?")  # answered, but nobody waits for it
        assert _wait_for(lambda: not device._replies.empty())
        assert device.query("f?") == ["422"]
    finally:
        device.close()


def test_verbose_lines_become_data_points_and_answers_do_not() -> None:
    device, transport = _p2()
    try:
        columns = len(ds.PARTECTOR2_DATA_STRUCTURE) - 1  # the timestamp is ours
        for _ in range(3):
            transport.emit(columns)
        transport.emit(columns + 1)  # not a known layout: dropped
        assert device.query("N?") == ["8617"]
        assert _wait_for(lambda: len(device._points) == 3)

        points = device.get_data()
        assert len(points) == 3
        assert device.get_data() == []
        assert points[0].serial_number == 8617
        assert points[0].firmware_version == 422
        assert points[0].connection_type == ConnectionType.SERIAL
        assert points[0].ldsa == 1.0
        assert points[0].unix_timestamp is not None and points[0].unix_timestamp > 1e12
    finally:
        device.close()


def test_legacy_layout_cuts_extra_columns_off() -> None:
    transport = FakeTransport(serial_number=24, firmware=100)
    device = Partector1(transport=transport)  # type: ignore[arg-type]
    try:
        transport.emit(len(ds.PARTECTOR1_DATA_STRUCTURE_V_LEGACY) + 5)
        assert _wait_for(lambda: len(device._points) == 1)
        assert device.get_data()[0].device_type == DeviceType.P1
    finally:
        device.close()


def test_optional_columns_do_not_leak_into_the_module_layouts() -> None:
    before = copy.deepcopy(ds.PARTECTOR2_DATA_STRUCTURE)
    before_pro = copy.deepcopy(ds.PARTECTOR2_PRO_DATA_STRUCTURE_V336)

    with_extras, _ = _p2(gain_test_active=True, output_pulse_diagnostics=True)
    plain, _ = _p2()
    pro, _ = _pro(gain_test_active=True, output_pulse_diagnostics=True)
    try:
        assert "electrometer_1_gain" in with_extras._data_structure
        assert "diffusion_current_delay_on" in with_extras._data_structure
        assert plain._data_structure == before
        assert "electrometer_1_gain" in pro._data_structure
        assert with_extras.is_settling and not plain.is_settling
    finally:
        for device in (with_extras, plain, pro):
            device.close()

    assert ds.PARTECTOR2_DATA_STRUCTURE == before
    assert ds.PARTECTOR2_PRO_DATA_STRUCTURE_V336 == before_pro


def test_old_p2_firmware_gets_no_diagnostics() -> None:
    device, transport = _p2(firmware=275, gain_test_active=True, output_pulse_diagnostics=True)
    try:
        assert device._data_structure == ds.PARTECTOR2_DATA_STRUCTURE_V265_V275
        assert "opd01!" not in transport.written
        assert not device.is_settling
    finally:
        device.close()


def test_every_p2_pro_column_lands_on_a_data_point_field_or_is_dropped() -> None:
    device, transport = _pro()
    try:
        layout = device._data_structure
        transport._lines.put("\t".join(str(i) for i in range(1, len(layout))))
        assert _wait_for(lambda: len(device._points) == 1)
        point = device.get_data()[0]

        assert point.particle_surface == float(list(layout).index("particle_surface"))
        assert point.steps_inversion == list(layout).index("steps_inversion")
        assert point.particle_number_300nm == list(layout).index("particle_number_300nm")
        # columns without a field are parsed for the line length but not attached
        assert not hasattr(point, "flow_from_phase_angle")
    finally:
        device.close()


def test_p2_pro_modes() -> None:
    device, transport = _pro()
    try:
        # the default is the size distribution mode, paced by the device
        assert device.sample_rate_hz is None
        assert device._data_structure == ds.PARTECTOR2_PRO_DATA_STRUCTURE_V336
        assert transport.written[-6:] == [
            "X0006!", "M0004!", "A0002!", "opd00!", "h2000!", "e0000!",
        ]  # fmt: skip

        # a rate switches to the plain P2 mode; the mode switch resets the
        # device settings, so they follow it
        device.set_sample_rate(10)
        assert device.sample_rate_hz == 10
        assert device._data_structure == ds.PARTECTOR2_DATA_STRUCTURE
        switch = transport.written.index("M0000!")
        assert transport.written[switch:] == [
            "M0000!", "A0002!", "opd00!", "h2000!", "e0000!", "X0002!",
        ]  # fmt: skip

        # another rate in the P2 mode is just the rate
        device.set_sample_rate(100)
        assert transport.written[-1] == "X0003!"

        # off keeps the mode, None is back to the size distribution
        device.set_sample_rate(0)
        assert transport.written[-1] == "X0000!"
        assert device.sample_rate_hz == 0
        device.set_sample_rate(None)
        assert device.sample_rate_hz is None
        assert transport.written[-6:-4] == ["X0006!", "M0004!"]
        assert device._data_structure == ds.PARTECTOR2_PRO_DATA_STRUCTURE_V336
    finally:
        device.close()


def test_p2_pro_can_start_in_the_p2_mode() -> None:
    device, transport = _pro(sample_rate_hz=100)
    try:
        assert device.sample_rate_hz == 100
        assert "M0000!" in transport.written
        assert transport.written[-1] == "X0003!"
        assert device._data_structure == ds.PARTECTOR2_DATA_STRUCTURE
    finally:
        device.close()


def test_close_resets_the_device_and_further_commands_fail() -> None:
    device, transport = _p2()
    device.close()

    assert transport.written[-4:] == ["X0000!", "opd00!", "h2000!", "e0000!"]
    assert not device.is_connected
    assert not transport.is_open
    with pytest.raises(ConnectionError):
        device.write("X0001!")
    with pytest.raises(ConnectionError):
        device.query("N?")


def test_an_unplugged_device_reports_disconnected() -> None:
    device, transport = _p2()
    transport.unplug()
    assert _wait_for(lambda: not device.is_connected)
    device.close()  # must not raise or hang


def test_a_silent_device_is_probed_and_dropped_if_it_does_not_answer() -> None:
    device, transport = _p2(sample_rate_hz=0)
    try:
        device.SILENCE_BEFORE_PROBE_SECONDS = 0.05
        device.PROBE_TIMEOUT_SECONDS = 0.1

        time.sleep(0.3)  # silent, but it answers the probe
        assert device.is_connected
        assert transport.written.count("N?") > 3

        transport.mute = True
        assert _wait_for(lambda: not device.is_connected)
    finally:
        device.close()

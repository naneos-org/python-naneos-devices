"""Hardware-free tests for the serial data-structure selection."""

import copy

from naneos.data_point import ConnectionType
from naneos.partector.blueprints import _data_structure as ds
from naneos.partector.partector2 import Partector2
from naneos.partector.partector2_pro import Partector2Pro


def _bare_device(cls, fw: int, gain_test: bool, pulse_diag: bool):
    """Build a device object without opening a serial port."""
    device = object.__new__(cls)
    device._init_variables()
    device._fw = fw
    device._sn = 1234
    device._GAIN_TEST_ACTIVE = gain_test
    device._OUTPUT_PULSE_DIAGNOSTICS = pulse_diag
    device._connected = True
    device._write_line = lambda line: None  # type: ignore[assignment]
    return device


def test_p2_optional_columns_do_not_leak_into_module_structure() -> None:
    before = copy.deepcopy(ds.PARTECTOR2_DATA_STRUCTURE)

    with_extras = _bare_device(Partector2, fw=320, gain_test=True, pulse_diag=True)
    with_extras._init_serial_data_structure()

    assert "electrometer_1_gain" in with_extras._data_structure
    assert "diffusion_current_delay_on" in with_extras._data_structure
    assert ds.PARTECTOR2_DATA_STRUCTURE == before

    plain = _bare_device(Partector2, fw=320, gain_test=False, pulse_diag=False)
    plain._init_serial_data_structure()

    assert plain._data_structure == before


def test_p2_pro_optional_columns_do_not_leak_into_module_structure() -> None:
    before_pro = copy.deepcopy(ds.PARTECTOR2_PRO_DATA_STRUCTURE_V336)
    before_std = copy.deepcopy(ds.PARTECTOR2_DATA_STRUCTURE)

    pro_mode = _bare_device(Partector2Pro, fw=340, gain_test=True, pulse_diag=True)
    pro_mode._set_verbose_freq(6)
    assert "electrometer_1_gain" in pro_mode._data_structure
    assert ds.PARTECTOR2_PRO_DATA_STRUCTURE_V336 == before_pro

    std_mode = _bare_device(Partector2Pro, fw=340, gain_test=True, pulse_diag=True)
    std_mode._set_verbose_freq(1)
    assert "electrometer_1_gain" in std_mode._data_structure
    assert ds.PARTECTOR2_DATA_STRUCTURE == before_std


def test_device_info_has_defaults_before_it_is_read() -> None:
    device = object.__new__(Partector2)
    device._init_variables()

    assert device._fw == 0
    assert device._integration_time == 0


def test_every_p2_pro_column_lands_on_a_data_point_field_or_is_dropped() -> None:
    device = _bare_device(Partector2Pro, fw=340, gain_test=False, pulse_diag=False)
    device._set_verbose_freq(6)

    structure = device._data_structure
    line = [1_700_000_000_000] + [str(i) for i in range(1, len(structure))]

    point = device._create_naneos_device_point(device._cast_splitted_input_string(line))

    assert point.serial_number == 1234
    assert point.connection_type == ConnectionType.SERIAL
    assert point.unix_timestamp == 1_700_000_000_000
    assert point.particle_surface == float(list(structure).index("particle_surface"))
    assert point.steps_inversion == list(structure).index("steps_inversion")
    assert point.particle_number_300nm == list(structure).index("particle_number_300nm")
    # columns without a field are parsed for the line length but not attached
    assert not hasattr(point, "flow_from_phase_angle")
    assert "particle_surface" in point.to_dict()


def test_write_line_returns_the_device_answer_or_an_empty_list() -> None:
    device = _bare_device(Partector2, fw=320, gain_test=False, pulse_diag=False)
    device._init_data_structures()
    device.thread_event = __import__("threading").Event()
    sent: list[str] = []

    def fake_write_line(line: str) -> None:  # the device answers the name query
        sent.append(line)
        if line == "name?":
            device._queue_info.append([1, "P2pro"])

    device._write_line = fake_write_line  # type: ignore[assignment]

    assert device.write_line("name?") == [1, "P2pro"]
    assert sent == ["name?"]

    assert device.write_line("X0000!", 0) == []  # fire and forget
    assert sent == ["name?", "X0000!"]

    device.SERIAL_RETRIES = 1
    assert device.write_line("N?") == []  # nothing came back within the timeout

    device._connected = False
    assert device.write_line("N?") == []

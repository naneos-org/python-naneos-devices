"""Serial line layouts per device family and firmware.

Each dict maps the tab separated columns of one verbose line, in order, to
the type used to parse them. Keys that are fields of NaneosDeviceDataPoint
end up on the data point; the others are parsed only to match the line length.
"""

# Re-exported for code written against naneos-devices <= 1.1.x.
from naneos.data_point import ConnectionType, DeviceType, NaneosDeviceDataPoint  # noqa: F401
from naneos.frames import (  # noqa: F401
    add_to_existing_naneos_data,
    sort_and_clean_naneos_data,
)

SerialLayout = dict[str, type[int] | type[float]]

PARTECTOR1_DATA_STRUCTURE_V_LEGACY: SerialLayout = {
    "unix_timestamp": int,
    "runtime_min": float,
    "battery_voltage": float,
    "diffusion_current": float,
    "corona_voltage": float,
    "electrometer_1_amplitude": float,  # TODO: check with martin
    "DAC": float,  # TODO: check with martin
    "HVon": int,  # TODO: check with martin
    "idiffset": float,  # TODO: check with martin
    "flow_from_dp": float,
    "ldsa": float,
    "temperature": float,
    "relative_humidity": float,
    "device_status": int,
}

# Optional column blocks a P2 / P2 Pro appends when the feature is switched on.
PARTECTOR2_GAIN_TEST_ADDITIONAL_DATA_STRUCTURE: SerialLayout = {
    "electrometer_1_gain": float,
    "electrometer_2_gain": float,
}

PARTECTOR2_OUTPUT_PULSE_DIAGNOSTIC_ADDITIONAL_DATA_STRUCTURE: SerialLayout = {
    "diffusion_current_delay_on": int,  # cs
    "diffusion_current_delay_off": int,  # cs
    "diffusion_current_average": float,  # nA
    "corona_voltage_onset": int,  # V
    "diffusion_current_stddev": float,  # nA
    "diffusion_current_max": float,  # nA
}

# The P2 line has had this layout since firmware 295; it is also what
# unknown ("legacy") firmware versions are parsed with.
PARTECTOR2_DATA_STRUCTURE: SerialLayout = {
    "unix_timestamp": int,
    "runtime_min": float,
    "diffusion_current": float,
    "corona_voltage": int,
    "hires_adc1": float,
    "hires_adc2": float,
    "electrometer_1_amplitude": float,
    "electrometer_2_amplitude": float,
    "temperature": float,
    "relative_humidity": int,
    "device_status": int,
    "deposition_voltage": int,
    "battery_voltage": float,
    "flow_from_dp": float,
    "ldsa": float,
    "average_particle_diameter": float,
    "particle_number_concentration": int,
    "differential_pressure": int,
    "ambient_pressure": float,
}

# Firmware 265 and 275 send one trailing column more.
PARTECTOR2_DATA_STRUCTURE_V265_V275: SerialLayout = {
    **PARTECTOR2_DATA_STRUCTURE,
    "lag": int,  # not used anymore
}


def _p2_pro_layout(flow_column: str, flow_type: type[int] | type[float]) -> SerialLayout:
    """The P2 Pro size-distribution line; only one column differs between firmwares."""
    return {
        "unix_timestamp": int,
        "runtime_min": float,
        "particle_number_concentration": int,
        "average_particle_diameter": float,
        "ldsa": float,
        "particle_surface": float,
        "particle_mass": float,
        "sigma_size_dist": float,
        "diffusion_current": float,
        "corona_voltage": int,
        "deposition_voltage": int,
        "temperature": float,
        "relative_humidity": int,
        "ambient_pressure": float,
        "flow_from_dp": float,
        "battery_voltage": float,
        "pump_current": float,
        "device_status": int,
        flow_column: flow_type,
        "steps_inversion": int,
        "particle_number_10nm": int,
        "particle_number_16nm": int,
        "particle_number_26nm": int,
        "particle_number_43nm": int,
        "particle_number_70nm": int,
        "particle_number_114nm": int,
        "particle_number_185nm": int,
        "particle_number_300nm": int,
        "current_dist_0": float,
        "current_dist_1": float,
        "current_dist_2": float,
        "current_dist_3": float,
        "current_dist_4": float,
    }


PARTECTOR2_PRO_DATA_STRUCTURE_V311: SerialLayout = _p2_pro_layout("pump_pwm", int)
# From firmware 336 the pump PWM column is replaced by the flow from the
# phase angle, which is parsed for the line length but has no data point field.
PARTECTOR2_PRO_DATA_STRUCTURE_V336: SerialLayout = _p2_pro_layout("flow_from_phase_angle", float)

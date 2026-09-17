"""DataFrame -> protobuf conversion for the upload."""

import pandas as pd

from naneos.frames import device_type_of
from naneos.logger import get_naneos_logger
from naneos.protobuf import protoV1_pb2 as pbScheme

logger = get_naneos_logger(__name__)

# (frame column, DevicePoint field, scale). The backend stores integers, so
# each value is multiplied by the scale of its field (see protoV1.proto) and
# rounded. Columns missing from a row leave the optional field unset.
DEVICE_POINT_FIELDS: tuple[tuple[str, str, float], ...] = (
    ("device_status", "device_status", 1),
    ("firmware_version", "firmware_version", 1),
    ("ldsa", "ldsa", 100),
    ("particle_number_concentration", "particle_number_concentration", 1),
    ("average_particle_diameter", "average_particle_diameter", 1),
    ("particle_mass", "particle_mass", 100),
    ("particle_surface", "particle_surface", 100),
    ("diffusion_current", "diffusion_current", 100),
    ("diffusion_current_offset", "diffusion_current_offset", 100),
    ("diffusion_current_stddev", "diffusion_current_stddev", 100),
    ("diffusion_current_delay_on", "diffusion_current_delay_on", 1),
    ("diffusion_current_delay_off", "diffusion_current_delay_off", 1),
    ("corona_voltage", "corona_voltage", 1),
    ("electrometer_1_amplitude", "electrometer_1_offset", 10),
    ("electrometer_2_amplitude", "electrometer_2_offset", 10),
    ("electrometer_1_gain", "electrometer_1_gain", 100),
    ("electrometer_2_gain", "electrometer_2_gain", 100),
    ("temperature", "temperature", 1),
    ("relative_humidity", "relative_humidity", 1),
    ("flow_from_dp", "flow", 1000),
    ("deposition_voltage", "deposition_voltage", 1),
    ("battery_voltage", "battery_voltage", 100),
    ("ambient_pressure", "ambient_pressure", 10),
    ("channel_pressure", "channel_pressure", 10),
    ("differential_pressure", "differential_pressure", 10),
    ("pump_voltage", "pump_voltage", 100),
    ("pump_current", "pump_current", 1000),
    ("pump_pwm", "pump_pwm", 1),
    ("particle_number_10nm", "particle_number_10nm", 1),
    ("particle_number_16nm", "particle_number_16nm", 1),
    ("particle_number_26nm", "particle_number_26nm", 1),
    ("particle_number_43nm", "particle_number_43nm", 1),
    ("particle_number_70nm", "particle_number_70nm", 1),
    ("particle_number_114nm", "particle_number_114nm", 1),
    ("particle_number_185nm", "particle_number_185nm", 1),
    ("particle_number_300nm", "particle_number_300nm", 1),
    ("sigma_size_dist", "sigma_size_dist", 100),
    ("steps_inversion", "steps_inversion", 1),
    ("current_dist_0", "current_dist_0", 100_000),
    ("current_dist_1", "current_dist_1", 100_000),
    ("current_dist_2", "current_dist_2", 100_000),
    ("current_dist_3", "current_dist_3", 100_000),
    ("current_dist_4", "current_dist_4", 100_000),
    ("supply_voltage_5V", "supply_voltage_5V", 10),
    ("positive_voltage_3V3", "positive_voltage_3V3", 10),
    ("negative_voltage_3V3", "negative_voltage_3V3", 10),
    ("usb_cc_voltage", "usb_cc_voltage", 10),
)

# Unsigned on the wire; a negative reading is clamped instead of wrapping.
NON_NEGATIVE_COLUMNS = frozenset(
    {"diffusion_current", "diffusion_current_delay_on", "diffusion_current_delay_off"}
)

# Not implemented in the protobuf schema yet: diffusion_current_average,
# diffusion_current_max, corona_voltage_onset.


def create_combined_entry(
    devices: list[pbScheme.Device],
    abs_timestamp: int,
    gateway_points: list[pbScheme.GatewayPointLegacy] | None = None,
    position_points: list[pbScheme.PositionPoint] | None = None,
    wind_points: list[pbScheme.WindPoint] | None = None,
) -> pbScheme.CombinedData:
    combined = pbScheme.CombinedData()
    combined.abs_timestamp = abs_timestamp

    combined.devices.extend(devices)

    if gateway_points is not None:
        combined.gateway_points_legacy.extend(gateway_points)

    if position_points is not None:
        combined.position_points.extend(position_points)

    if wind_points is not None:
        combined.wind_points.extend(wind_points)

    return combined


def create_proto_device(sn: int, abs_time: int, df: pd.DataFrame) -> pbScheme.Device:
    """One Device message from a frame indexed by unix seconds."""
    device = pbScheme.Device()
    device.type = int(device_type_of(df))
    device.serial_number = sn

    device_points = [_create_device_point(row, abs_time) for _, row in df.iterrows()]
    device.device_points.extend(point for point in device_points if point is not None)

    return device


def _create_device_point(ser: pd.Series, abs_time: int) -> pbScheme.DevicePoint | None:
    try:
        ser = ser.dropna()

        if not isinstance(ser.name, int):
            raise ValueError("Timestamp is not an int!")

        device_point = pbScheme.DevicePoint()
        device_point.timestamp = abs_time - ser.name

        for column, field, scale in DEVICE_POINT_FIELDS:
            if column not in ser:
                continue
            value = ser[column]
            if column in NON_NEGATIVE_COLUMNS:
                value = max(value, 0)
            setattr(device_point, field, int(round(value * scale)))

    except Exception as e:
        logger.warning(f"Could not convert a data point for upload: {e}")
        return None

    return device_point

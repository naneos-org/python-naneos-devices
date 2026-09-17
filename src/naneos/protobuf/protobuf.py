"""DataFrame -> protobuf conversion for the upload (schema: proto_v2.proto).

The schema describes itself: every field carries its scale as a field option
(wire value = value * scale), so the conversion is built from the descriptor
and only the names that differ between frame and schema are listed here.
"""

from dataclasses import dataclass

import pandas as pd
from google.protobuf.descriptor import FieldDescriptor

from naneos.frames import device_type_of
from naneos.logger import get_naneos_logger
from naneos.protobuf import proto_v2_pb2 as pb

logger = get_naneos_logger(__name__)

# Schema field -> frame column, where the names differ.
COLUMN_OF_FIELD: dict[str, str] = {
    "surface": "particle_surface",
    "flow": "flow_from_dp",
    "electrometer_gain": "electrometer_1_gain",
    "electrometer_amplitude": "electrometer_1_amplitude",
    "electrometer_amplitude_2": "electrometer_2_amplitude",
    "diffusion_current_avg": "diffusion_current_average",
}

# Schema fields no device of this package reports.
FIELDS_WITHOUT_COLUMN = frozenset({"cs_status", "electrometer_offset", "electrometer_2_offset"})

# Frame columns whose unit differs from the unit of the schema field:
# value in schema unit = column value * factor.
COLUMN_UNIT_FACTOR: dict[str, float] = {
    "diffusion_current_delay_on": 0.01,  # cs -> s
    "diffusion_current_delay_off": 0.01,  # cs -> s
}

_UNSIGNED_TYPES = frozenset(
    {
        FieldDescriptor.TYPE_UINT32,
        FieldDescriptor.TYPE_UINT64,
        FieldDescriptor.TYPE_FIXED32,
        FieldDescriptor.TYPE_FIXED64,
    }
)


@dataclass(frozen=True)
class _PointField:
    group: str  # the sub message of DevicePoint, e.g. "status_data"
    name: str
    column: str
    factor: float  # column value -> wire value
    unsigned: bool


def _point_fields() -> tuple[_PointField, ...]:
    fields: list[_PointField] = []
    for group in pb.DevicePoint.DESCRIPTOR.fields:
        if group.message_type is None:
            continue  # the timestamp
        for field in group.message_type.fields:
            if field.name in FIELDS_WITHOUT_COLUMN:
                continue
            column = COLUMN_OF_FIELD.get(field.name, field.name)
            # The generated stub types the extension as a plain FieldDescriptor.
            options = field.GetOptions()
            scale: float = options.Extensions[pb.scale] or 1.0  # type: ignore[index]  # unset -> 0
            fields.append(
                _PointField(
                    group=group.name,
                    name=field.name,
                    column=column,
                    factor=scale * COLUMN_UNIT_FACTOR.get(column, 1.0),
                    unsigned=field.type in _UNSIGNED_TYPES,
                )
            )
    return tuple(fields)


POINT_FIELDS = _point_fields()


def create_combined_entry(devices: list[pb.Device], abs_timestamp: int) -> pb.CombinedData:
    combined = pb.CombinedData()
    combined.abs_timestamp = abs_timestamp
    combined.devices.extend(devices)
    return combined


def create_proto_device(sn: int, abs_time: int, df: pd.DataFrame) -> pb.Device:
    """One Device message from a frame indexed by unix seconds."""
    device = pb.Device()
    device.type = int(device_type_of(df))  # type: ignore[assignment]  # same numbers as pb.DeviceType
    device.serial_number = sn

    device_points = [_create_device_point(row, abs_time) for _, row in df.iterrows()]
    device.device_points.extend(point for point in device_points if point is not None)

    return device


def _create_device_point(ser: pd.Series, abs_time: int) -> pb.DevicePoint | None:
    """Columns missing from a row leave their field unset.

    The two size distribution groups have no per-field presence: they are only
    set when the row carries at least one of their columns, and a column that
    is missing then reads back as 0.
    """
    try:
        ser = ser.dropna()

        if not isinstance(ser.name, int):
            raise ValueError("Timestamp is not an int!")

        device_point = pb.DevicePoint()
        device_point.timestamp = abs_time - ser.name

        for field in POINT_FIELDS:
            if field.column not in ser:
                continue
            value = int(round(ser[field.column] * field.factor))
            if field.unsigned:
                value = max(value, 0)  # a negative reading is clamped instead of wrapping
            setattr(getattr(device_point, field.group), field.name, value)

    except Exception as e:
        logger.warning(f"Could not convert a data point for upload: {e}")
        return None

    return device_point

"""DataFrame -> protobuf conversion for the upload (schema: proto_v2.proto).

The schema describes itself: every field carries its scale as a field option
(wire value = value * scale), so the conversion is built from the descriptor
and only the names that differ between frame and schema are listed here.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd
from google.protobuf.descriptor import FieldDescriptor

from naneos.diagnostics import PulseForm, UiCurve
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


def _scale_of(descriptor: Any, field_name: str) -> float:
    """The scale option of a schema field; unset reads back as 0 and means 1."""
    options = descriptor.fields_by_name[field_name].GetOptions()
    return options.Extensions[pb.scale] or 1.0  # type: ignore[index]


def create_ui_curve(curve: UiCurve) -> pb.UiCurve:
    """One UiCurve message; the currents go on the wire at the scale of the schema."""
    message = pb.UiCurve()
    message.type = int(curve.device_type)  # type: ignore[assignment]  # same numbers as pb.DeviceType
    message.abs_timestamp = curve.unix_timestamp
    message.serial_number = curve.serial_number
    message.U_values.extend(max(int(round(u)), 0) for u in curve.voltages)
    scale = _scale_of(pb.UiCurve.DESCRIPTOR, "I_values")
    message.I_values.extend(max(int(round(i * scale)), 0) for i in curve.currents)
    return message


def create_pulse_form(form: PulseForm) -> pb.PulseForm:
    """One PulseForm message.

    The schema calls the field U_values in mV, but what the devices send, and
    what the backend stores, is the electrometer current in nA at scale 100.
    """
    message = pb.PulseForm()
    message.type = int(form.device_type)  # type: ignore[assignment]  # same numbers as pb.DeviceType
    message.abs_timestamp = form.unix_timestamp
    message.serial_number = form.serial_number
    scale = _scale_of(pb.PulseForm.DESCRIPTOR, "U_values")
    message.U_values.extend(max(int(round(i * scale)), 0) for i in form.currents)
    return message


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

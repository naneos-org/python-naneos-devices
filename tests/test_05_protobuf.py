"""Hardware-free tests for the DataFrame -> protobuf conversion."""

import pandas as pd

from naneos.cloud.protobuf import create_proto_device
from naneos.data_point import DeviceType


def _frame(**columns) -> pd.DataFrame:
    df = pd.DataFrame({"unix_timestamp": [1_700_000_000, 1_700_000_001], **columns})
    return df.set_index("unix_timestamp")


def test_every_mapped_column_reaches_the_device_point() -> None:
    df = _frame(
        device_type=[DeviceType.P2PRO] * 2,
        ldsa=[12.34, 56.78],
        particle_surface=[1.5, 2.5],
        steps_inversion=[3, 4],
        usb_cc_voltage=[5.0, 5.1],
    )

    device = create_proto_device(sn=8617, abs_time=1_700_000_010, df=df)

    assert device.serial_number == 8617
    assert device.type == DeviceType.P2PRO
    assert len(device.device_points) == 2

    first, second = device.device_points
    assert first.timestamp == 10
    assert first.ldsa == 1234
    assert first.particle_surface == 150
    assert first.steps_inversion == 3
    assert first.usb_cc_voltage == 50
    assert first.HasField("usb_cc_voltage")
    assert second.timestamp == 9
    assert second.usb_cc_voltage == 51


def test_missing_columns_leave_optional_fields_unset() -> None:
    device = create_proto_device(sn=1, abs_time=1_700_000_010, df=_frame(ldsa=[1.0, 2.0]))

    point = device.device_points[0]
    assert point.HasField("ldsa")
    assert not point.HasField("usb_cc_voltage")
    assert not point.HasField("particle_surface")


def test_field_table_only_names_existing_columns_and_proto_fields() -> None:
    """Guards against typos like the leading space that once hid usb_cc_voltage."""
    from naneos.cloud import protoV1_pb2
    from naneos.cloud.protobuf import DEVICE_POINT_FIELDS, NON_NEGATIVE_COLUMNS
    from naneos.data_point import NaneosDeviceDataPoint

    columns = set(NaneosDeviceDataPoint.__dataclass_fields__)
    proto_fields = set(protoV1_pb2.DevicePoint.DESCRIPTOR.fields_by_name)

    for column, field, scale in DEVICE_POINT_FIELDS:
        assert column in columns, column
        assert field in proto_fields, field
        assert scale > 0
    assert len({column for column, _, _ in DEVICE_POINT_FIELDS}) == len(DEVICE_POINT_FIELDS)
    assert NON_NEGATIVE_COLUMNS <= {column for column, _, _ in DEVICE_POINT_FIELDS}


def test_negative_readings_are_clamped_and_values_rounded() -> None:
    df = _frame(diffusion_current=[-0.5, 12.345], diffusion_current_delay_on=[-3, 2.6])

    first, second = create_proto_device(sn=1, abs_time=1_700_000_010, df=df).device_points

    assert first.diffusion_current == 0
    assert first.diffusion_current_delay_on == 0
    assert second.diffusion_current == 1234  # round(1234.5) -> banker's rounding, as before
    assert second.diffusion_current_delay_on == 3

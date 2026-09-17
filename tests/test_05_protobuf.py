"""Hardware-free tests for the DataFrame -> protobuf conversion."""

import pandas as pd

from naneos.data_point import DeviceType
from naneos.protobuf import proto_v2_pb2
from naneos.protobuf.protobuf import create_proto_device


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
        flow_from_dp=[0.5, 0.5],
        temperature=[-3.4, 21.0],
    )

    device = create_proto_device(sn=8617, abs_time=1_700_000_010, df=df)

    assert device.serial_number == 8617
    assert device.type == DeviceType.P2PRO
    assert len(device.device_points) == 2

    first, second = device.device_points
    assert first.timestamp == 10
    assert first.user_plan_data.ldsa == 1234
    assert first.user_plan_data.surface == 150
    assert first.status_data_size_dist.steps_inversion == 3
    assert first.status_data.usb_cc_voltage == 50
    assert first.status_data.HasField("usb_cc_voltage")
    assert first.status_data.flow == 500
    assert first.status_data.temperature == -3  # signed in the schema
    assert second.timestamp == 9
    assert second.status_data.usb_cc_voltage == 51


def test_missing_columns_leave_fields_and_groups_unset() -> None:
    device = create_proto_device(sn=1, abs_time=1_700_000_010, df=_frame(ldsa=[1.0, 2.0]))

    point = device.device_points[0]
    assert point.user_plan_data.HasField("ldsa")
    assert not point.user_plan_data.HasField("surface")
    assert not point.HasField("status_data")
    # the size distribution groups have no per-field presence, only the group tells
    assert not point.HasField("user_size_dist_data")
    assert not point.HasField("status_data_size_dist")


def test_size_distribution_group_is_set_with_its_columns() -> None:
    df = _frame(particle_number_70nm=[760, 770], current_dist_0=[0.00123, 0.002])

    point = create_proto_device(sn=1, abs_time=1_700_000_010, df=df).device_points[0]

    assert point.HasField("user_size_dist_data")
    assert point.user_size_dist_data.particle_number_70nm == 760
    assert point.user_size_dist_data.particle_number_10nm == 0
    assert point.status_data_size_dist.current_dist_0 == 123


def test_scales_come_from_the_schema_and_every_column_exists() -> None:
    """Guards against typos like the leading space that once hid usb_cc_voltage."""
    from naneos.data_point import NaneosDeviceDataPoint
    from naneos.protobuf.protobuf import (
        COLUMN_OF_FIELD,
        COLUMN_UNIT_FACTOR,
        FIELDS_WITHOUT_COLUMN,
        POINT_FIELDS,
    )

    columns = set(NaneosDeviceDataPoint.__dataclass_fields__)
    by_name = {field.name: field for field in POINT_FIELDS}

    for field in POINT_FIELDS:
        assert field.column in columns, field.column
        assert field.factor > 0
    assert len({field.column for field in POINT_FIELDS}) == len(POINT_FIELDS)

    assert by_name["ldsa"].factor == 100
    assert by_name["current_dist_0"].factor == 100_000
    assert by_name["electrometer_amplitude"].factor == 16
    assert by_name["device_status"].factor == 1  # no scale option in the schema
    assert not by_name["temperature"].unsigned
    assert by_name["flow"].column == "flow_from_dp"

    # the hand written tables must not rot when the schema changes
    schema_fields = {
        field.name
        for group in proto_v2_pb2.DevicePoint.DESCRIPTOR.fields
        if group.message_type is not None
        for field in group.message_type.fields
    }
    assert set(COLUMN_OF_FIELD) <= schema_fields
    assert FIELDS_WITHOUT_COLUMN <= schema_fields
    assert set(COLUMN_UNIT_FACTOR) <= columns


def test_negative_readings_are_clamped_and_values_rounded() -> None:
    df = _frame(diffusion_current=[-0.5, 12.345], diffusion_current_delay_on=[-3, 2.6])

    first, second = create_proto_device(sn=1, abs_time=1_700_000_010, df=df).device_points

    assert first.status_data.diffusion_current == 0
    assert first.status_data.diffusion_current_delay_on == 0
    assert second.status_data.diffusion_current == 1234  # round(1234.5): banker's rounding
    # the column is in centiseconds, the schema in seconds * 100: the same number
    assert second.status_data.diffusion_current_delay_on == 3

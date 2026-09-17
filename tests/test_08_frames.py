"""Hardware-free tests for naneos.frames."""

import logging

import pandas as pd

from naneos.data_point import ConnectionType, DeviceType, NaneosDeviceDataPoint
from naneos.frames import (
    MAX_BUFFER_SECONDS,
    add_data_points_to_dict,
    device_type_of,
    sort_and_clean_naneos_data,
    to_pandas_df,
)
from naneos.partector.blueprints import _data_structure as serial_layouts

# Complete line layouts, plus the V320 layout extended by the two optional blocks.
SERIAL_LAYOUTS = [
    value
    for name, value in vars(serial_layouts).items()
    if name.startswith("PARTECTOR") and isinstance(value, dict) and "unix_timestamp" in value
] + [
    {
        **serial_layouts.PARTECTOR2_DATA_STRUCTURE,
        **serial_layouts.PARTECTOR2_OUTPUT_PULSE_DIAGNOSTIC_ADDITIONAL_DATA_STRUCTURE,
        **serial_layouts.PARTECTOR2_GAIN_TEST_ADDITIONAL_DATA_STRUCTURE,
    }
]


def _point(serial: int, ts: int, conn: ConnectionType, dev: DeviceType | None = None):
    return NaneosDeviceDataPoint(
        unix_timestamp=ts,
        serial_number=serial,
        connection_type=conn,
        device_type=dev,
        ldsa=float(ts),
    )


def test_every_serial_layout_converts_with_strict_dtypes(caplog) -> None:
    """The dtype mapping must fit the values every serial layout produces."""
    assert len(SERIAL_LAYOUTS) >= 6

    fields = NaneosDeviceDataPoint.__dataclass_fields__
    for layout in SERIAL_LAYOUTS:
        point = NaneosDeviceDataPoint(serial_number=1, connection_type=ConnectionType.SERIAL)
        for name, cast in layout.items():
            if name in fields:
                setattr(point, name, cast(7.5) if cast is float else cast(7))

        with caplog.at_level(logging.WARNING, logger="naneos.frames"):
            df = to_pandas_df([point])

        assert not df.empty
        assert "Could not apply" not in caplog.text
        assert str(df["runtime_min"].dtype) == "Float32"


def test_ble_style_point_with_none_device_type_converts(caplog) -> None:
    point = _point(1, 1000, ConnectionType.CONNECTED)  # device_type None until known

    with caplog.at_level(logging.WARNING, logger="naneos.frames"):
        df = to_pandas_df([point])

    assert "Could not apply" not in caplog.text
    assert str(df["device_type"].dtype) == "Int32"
    assert df["device_type"].isna().all()
    assert (df["connection_type"] == ConnectionType.CONNECTED).all()
    assert (df["connection_type"] == "connected").all()


def test_sort_and_clean_prefers_serial_over_connected() -> None:
    data = {
        1: to_pandas_df(
            [_point(1, 1000, ConnectionType.CONNECTED), _point(1, 500, ConnectionType.SERIAL)]
        ),
        2: to_pandas_df([_point(2, 1000, ConnectionType.CONNECTED)]),
    }

    cleaned = sort_and_clean_naneos_data(data)

    assert list(cleaned[1].index) == [500]
    assert list(cleaned[2].index) == [1000]


def test_sort_and_clean_serial_only_drops_devices_without_serial_rows() -> None:
    data = {1: to_pandas_df([_point(1, 1000, ConnectionType.CONNECTED)])}

    assert sort_and_clean_naneos_data(data, serial_only=[1]) == {}


def test_sort_and_clean_keeps_last_row_per_timestamp() -> None:
    a = _point(1, 1000, ConnectionType.CONNECTED)
    b = _point(1, 1000, ConnectionType.CONNECTED)
    b.ldsa = 99.0
    cleaned = sort_and_clean_naneos_data({1: to_pandas_df([a, b])})

    assert list(cleaned[1]["ldsa"]) == [99.0]


def test_sort_and_clean_settles_on_the_most_specific_device_type_without_dropping_rows() -> None:
    points = [
        _point(1, 1000, ConnectionType.CONNECTED, None),  # before the family is known
        _point(1, 2000, ConnectionType.CONNECTED, DeviceType.P2),
        _point(1, 3000, ConnectionType.CONNECTED, DeviceType.P2PRO),
    ]
    cleaned = sort_and_clean_naneos_data({1: to_pandas_df(points)})

    assert len(cleaned[1]) == 3
    assert (cleaned[1]["device_type"] == DeviceType.P2PRO).all()
    assert device_type_of(cleaned[1]) == DeviceType.P2PRO


def test_device_type_of_falls_back_to_p2() -> None:
    unknown = to_pandas_df([_point(1, 1000, ConnectionType.CONNECTED)])
    assert device_type_of(unknown) == DeviceType.P2
    assert device_type_of(pd.DataFrame({"ldsa": [1.0]})) == DeviceType.P2


def test_add_data_points_skips_unknown_serials() -> None:
    points = [_point(1, 1000, ConnectionType.SERIAL)]
    points.append(NaneosDeviceDataPoint(unix_timestamp=1, serial_number=None))

    devices = add_data_points_to_dict({}, points)

    assert list(devices) == [1]
    assert len(devices[1]) == 1


def test_add_data_points_caps_the_buffer_by_time_not_by_rows() -> None:
    window_ms = MAX_BUFFER_SECONDS * 1000

    # 1 Hz, ten seconds more than the window: the oldest ten seconds go.
    slow = [_point(1, ts, ConnectionType.SERIAL) for ts in range(0, window_ms + 10_000, 1000)]
    devices = add_data_points_to_dict({}, slow)
    assert len(devices[1]) == MAX_BUFFER_SECONDS
    assert devices[1].index[0] == 10_000

    # 100 Hz for ten seconds is far more rows, but well inside the window.
    fast = [_point(2, ts, ConnectionType.SERIAL) for ts in range(0, 10_000, 10)]
    devices = add_data_points_to_dict({}, fast)
    assert len(devices[2]) == 1000

"""Hardware-free tests for the frames the upload keeps and sends (prepare_frames)."""

import time

import pandas as pd
import pytest
from fake_transport import FakeTransport

from naneos.cloud.upload import (
    UPLOAD_COLUMNS,
    build_prepared_entry,
    prepare_frames,
    to_upload_frame,
)
from naneos.frames import to_pandas_df
from naneos.protobuf.protobuf import create_combined_entry, create_proto_device
from naneos.usb.partector.device import Partector2, Partector2Pro

T0_MS = 1_780_000_000_000
NOW = 1_780_001_000


def device_frame(cls, transport, rows: int, spacing_ms: int = 1000) -> pd.DataFrame:
    """Rows as a real device class parses them from the lines of a fake transport."""
    device = cls(transport=transport, gain_test_active=False, output_pulse_diagnostics=True)
    try:
        for i in range(rows):
            transport.emit(len(device._data_structure) - 1, value=str(1000 + i % 50))
        points = []
        deadline = time.time() + 5
        while len(points) < rows and time.time() < deadline:
            points += device.get_data()
            time.sleep(0.02)
    finally:
        device.close()
    assert len(points) == rows
    for i, point in enumerate(points):
        point.unix_timestamp = T0_MS + i * spacing_ms
    return to_pandas_df(points)


@pytest.fixture(scope="module")
def p2_frame() -> pd.DataFrame:
    return device_frame(Partector2, FakeTransport(8617, 422, "P2"), 90)


@pytest.fixture(scope="module")
def pro_frame() -> pd.DataFrame:
    return device_frame(Partector2Pro, FakeTransport(8764, 424, "P2pro"), 40)


def reference_message(frame: pd.DataFrame) -> bytes:
    """The message as it was built before frames were prepared: every column, only the 1 Hz step."""
    device = create_proto_device(1, NOW, to_upload_frame(frame.copy()))
    return create_combined_entry(devices=[device], abs_timestamp=NOW).SerializeToString()


def test_the_message_of_prepared_frames_is_the_message_of_the_full_frames(
    p2_frame, pro_frame
) -> None:
    for frame in (p2_frame, pro_frame):
        prepared = build_prepared_entry(prepare_frames({1: frame.copy()}), NOW).SerializeToString()
        assert prepared == reference_message(frame)
        assert len(prepared) > 1000  # rows really made it into the message


def test_values_at_a_rounding_edge_go_on_the_wire_as_before(p2_frame) -> None:
    """Storing floats as numpy float32 must not move a value across a rounding boundary."""
    frame = p2_frame.copy()
    values = [0.125, 2.675, 1.005, 0.285, 3.14159, 1234.565, 99.995, 0.045, 7.5e-3, 2.5]
    for column in ("ldsa", "particle_mass", "diffusion_current", "corona_voltage", "flow_from_dp"):
        if column in frame.columns:
            frame[column] = pd.array((values * 9)[: len(frame)], dtype="Float32")

    prepared = build_prepared_entry(prepare_frames({1: frame.copy()}), NOW).SerializeToString()

    assert prepared == reference_message(frame)


def test_prepared_frames_keep_only_columns_the_wire_has_and_that_hold_data(p2_frame) -> None:
    prepared = prepare_frames({1: p2_frame.copy()})[1]

    assert 0 < len(prepared.columns) < len(p2_frame.columns) / 2
    assert set(prepared.columns) <= set(UPLOAD_COLUMNS)
    assert prepared.notna().any().all()  # no column without data
    assert prepared.memory_usage(index=True).sum() < p2_frame.memory_usage(index=True).sum() / 2


def test_prepared_frames_are_plain_numpy_with_one_block_per_dtype(p2_frame, pro_frame) -> None:
    for frame in (p2_frame, pro_frame):
        prepared = prepare_frames({1: frame.copy()})[1]

        assert {str(dtype) for dtype in prepared.dtypes} <= {"float32", "float64"}
        assert prepared._mgr.nblocks <= 2  # not one block per column
        assert prepared.memory_usage(index=True, deep=True).sum() == (
            prepared.memory_usage(index=True).sum()
        )


def test_a_100_hz_frame_is_kept_as_one_row_per_second() -> None:
    frame = device_frame(Partector2, FakeTransport(8617, 422, "P2"), 300, spacing_ms=10)

    prepared = prepare_frames({1: frame})[1]

    assert len(frame) == 300
    assert len(prepared) in (3, 4)  # 3 s of data, the ends may straddle a second
    assert prepared.index.dtype == "int64"


def test_frames_of_several_snapshots_go_into_one_message_at_their_own_times(p2_frame) -> None:
    first = p2_frame.iloc[:30].copy()
    second = p2_frame.iloc[30:60].copy()
    merged = pd.concat([prepare_frames({1: first})[1], prepare_frames({1: second})[1]])

    message = build_prepared_entry({1: merged}, NOW)

    device = message.devices[0]
    seconds = sorted(NOW - point.timestamp for point in device.device_points)
    expected = sorted(int(round(t / 1000)) for t in p2_frame.index[:60])
    assert seconds == expected


def test_empty_frames_are_left_out() -> None:
    assert prepare_frames({1: pd.DataFrame()}) == {}


def test_a_request_with_many_rows_gets_more_time_up_to_what_the_gateway_waits(monkeypatch) -> None:
    from types import SimpleNamespace

    from naneos.cloud import upload as upload_module

    timeouts = []
    monkeypatch.setattr(
        upload_module.requests,
        "post",
        lambda url, headers, data, timeout: timeouts.append(timeout) or SimpleNamespace(),
    )

    def frames(rows: int) -> dict[int, pd.DataFrame]:
        index = pd.Index(range(NOW - rows, NOW), name="unix_timestamp")
        return {1: pd.DataFrame({"ldsa": 1.0}, index=index)}

    for rows in (13, 1000, 6000):
        upload_module.send_frames(frames(rows))

    assert timeouts[0] == pytest.approx(10.065)  # a normal request: what it always was, and a bit
    assert timeouts[1] == pytest.approx(15.0)
    assert timeouts[2] == 30  # the API gateway does not wait longer

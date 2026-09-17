"""Hardware-free tests for the frame preparation of the uploader."""

import pandas as pd

from naneos.cloud.upload import build_body, build_combined_entry, to_upload_frame


def _ms_frame(*timestamps_ms: int, ldsa: float = 1.0) -> pd.DataFrame:
    df = pd.DataFrame({"unix_timestamp": list(timestamps_ms), "ldsa": [ldsa] * len(timestamps_ms)})
    return df.set_index("unix_timestamp")


def test_upload_frame_rounds_milliseconds_to_whole_seconds() -> None:
    df = to_upload_frame(_ms_frame(1_700_000_000_400, 1_700_000_000_600))

    assert list(df.index) == [1_700_000_000, 1_700_000_001]
    assert df.index.name == "unix_timestamp"


def test_upload_frame_replaces_inf_with_zero() -> None:
    df = to_upload_frame(_ms_frame(1_700_000_000_000, ldsa=float("inf")))

    assert list(df["ldsa"]) == [0]


def test_upload_frame_merges_a_10hz_device_into_one_row_per_second() -> None:
    # 2 s at 10 Hz, off the half second so rounding is unambiguous
    timestamps = [1_700_000_000_030 + i * 100 for i in range(-5, 15)]
    df = pd.DataFrame(
        {
            "unix_timestamp": timestamps,
            "ldsa": [10.0] * 10 + [20.0] * 10,
            "device_status": [0] * 9 + [4] + [1, 2] + [0] * 8,
            "firmware_version": [320] * 20,
            "connection_type": ["serial"] * 20,
        }
    ).set_index("unix_timestamp")
    df = df.astype({"ldsa": "Float32", "device_status": "Int32", "firmware_version": "Int32"})

    out = to_upload_frame(df)

    assert list(out.index) == [1_700_000_000, 1_700_000_001]
    assert list(out["ldsa"]) == [10.0, 20.0]  # measurements are averaged
    assert list(out["device_status"]) == [4, 3]  # status bits are OR-ed, none is lost
    assert list(out["firmware_version"]) == [320, 320]
    assert list(out["connection_type"]) == ["serial", "serial"]
    assert out.dtypes.to_dict() == df.dtypes.to_dict()


def test_upload_never_exceeds_1hz_whatever_the_reading_rate() -> None:
    timestamps = [1_700_000_000_000 + i * 10 for i in range(300)]  # 3 s at 100 Hz
    data = {8617: _ms_frame(*timestamps)}

    combined = build_combined_entry(data, abs_time=1_700_000_010)

    points = combined.devices[0].device_points
    assert sorted(p.timestamp for p in points) == [7, 8, 9, 10]
    assert all(p.user_plan_data.ldsa == 100 for p in points)


def test_upload_frame_keeps_missing_values_missing_when_merging() -> None:
    df = pd.DataFrame(
        {
            "unix_timestamp": [1_700_000_000_000, 1_700_000_000_100, 1_700_000_000_200],
            "ldsa": [None, 4.0, 6.0],
            "particle_mass": [None, None, None],
            "device_status": [None, None, None],
        }
    ).set_index("unix_timestamp")
    df = df.astype({"ldsa": "Float32", "particle_mass": "Float32", "device_status": "Int32"})

    out = to_upload_frame(df)

    assert list(out["ldsa"]) == [5.0]
    assert out["particle_mass"].isna().all()
    assert out["device_status"].isna().all()


def test_combined_entry_has_relative_timestamps_per_device() -> None:
    data = {8617: _ms_frame(1_700_000_000_000), 24: _ms_frame(1_700_000_005_000)}

    combined = build_combined_entry(data, abs_time=1_700_000_010)

    assert combined.abs_timestamp == 1_700_000_010
    by_sn = {d.serial_number: d for d in combined.devices}
    assert by_sn[8617].device_points[0].timestamp == 10
    assert by_sn[24].device_points[0].timestamp == 5


def test_body_is_valid_json_with_a_utc_timestamp() -> None:
    import json

    body = json.loads(build_body("QUJD"))

    assert body["gateway"] == "python_webhook"
    assert body["data"] == "QUJD"
    assert body["published_at"].endswith("+00:00")

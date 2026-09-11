"""Hardware-free tests for the frame preparation of the uploader."""

import pandas as pd

from naneos.iotweb.naneos_upload_thread import NaneosUploadThread


def _ms_frame(*timestamps_ms: int, ldsa: float = 1.0) -> pd.DataFrame:
    df = pd.DataFrame({"unix_timestamp": list(timestamps_ms), "ldsa": [ldsa] * len(timestamps_ms)})
    return df.set_index("unix_timestamp")


def test_upload_frame_rounds_milliseconds_to_whole_seconds() -> None:
    df = NaneosUploadThread.to_upload_frame(_ms_frame(1_700_000_000_400, 1_700_000_000_600))

    assert list(df.index) == [1_700_000_000, 1_700_000_001]
    assert df.index.name == "unix_timestamp"


def test_upload_frame_replaces_inf_with_zero() -> None:
    df = NaneosUploadThread.to_upload_frame(_ms_frame(1_700_000_000_000, ldsa=float("inf")))

    assert list(df["ldsa"]) == [0]


def test_combined_entry_has_relative_timestamps_per_device() -> None:
    data = {8617: _ms_frame(1_700_000_000_000), 24: _ms_frame(1_700_000_005_000)}

    combined = NaneosUploadThread.build_combined_entry(data, abs_time=1_700_000_010)

    assert combined.abs_timestamp == 1_700_000_010
    by_sn = {d.serial_number: d for d in combined.devices}
    assert by_sn[8617].device_points[0].timestamp == 10
    assert by_sn[24].device_points[0].timestamp == 5


def test_body_is_valid_json_with_a_utc_timestamp() -> None:
    import json

    body = json.loads(NaneosUploadThread.get_body("QUJD"))

    assert body["gateway"] == "python_webhook"
    assert body["data"] == "QUJD"
    assert body["published_at"].endswith("+00:00")

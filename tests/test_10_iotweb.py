"""Tests against the naneos IoT service. They need internet access and a token,
so they are marked `network` and skipped by default: `uv run pytest -m network`."""

import datetime as dt
import os
from pathlib import Path

import pandas as pd
import pytest

from naneos.cloud import upload_snapshot
from naneos.cloud.download import download_from_iotweb

pytestmark = pytest.mark.network

DATA_DIR = Path(__file__).parent / "data"


def test_download_8134() -> None:
    token = os.getenv("IOT_GUEST_TOKEN")
    if token is None:
        pytest.skip("IOT_GUEST_TOKEN is not set")

    df = download_from_iotweb(
        "iot_guest", "8134", dt.datetime(2025, 4, 1), dt.datetime(2025, 4, 7), token
    )

    assert len(df) == 206545


def test_upload_recorded_frames() -> None:
    data = {
        777: pd.read_pickle(DATA_DIR / "p2_pro_test_data.pkl"),
        666: pd.read_pickle(DATA_DIR / "p2_test_data.pkl"),
    }
    assert all(not df.empty for df in data.values())

    response = upload_snapshot(data)

    assert response.status_code == 200

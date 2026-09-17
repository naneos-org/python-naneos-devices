"""Upload of gathered snapshots to the naneos IoT service."""

import base64
import datetime
import json

import numpy as np
import pandas as pd
import requests

from naneos.frames import aggregate_duplicate_index
from naneos.protobuf import proto_v2_pb2 as pb
from naneos.protobuf.protobuf import create_combined_entry, create_proto_device

# The v2 API has one endpoint per message type. Only CombinedData is uploaded
# from here; UiCurve goes to /uicurve and PulseForm to /pulseform.
BASE_URL = "https://hg3zkburji.execute-api.eu-central-1.amazonaws.com/dev/proto/v2"
URL_COMBINED_DATA = f"{BASE_URL}/combined_data"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
TIMEOUT_SECONDS = 10


def upload_snapshot(data: dict[int, pd.DataFrame]) -> requests.Response:
    """Upload the frames of a snapshot, keyed by device serial number.

    Blocks for up to TIMEOUT_SECONDS. Raises requests.RequestException on
    network problems; HTTP errors are reported by the returned response.
    """
    abs_time = int(datetime.datetime.now().timestamp())
    combined_entry = build_combined_entry(data, abs_time)
    payload = base64.b64encode(combined_entry.SerializeToString()).decode()

    return requests.post(
        URL_COMBINED_DATA, headers=HEADERS, data=build_body(payload), timeout=TIMEOUT_SECONDS
    )


def build_body(upload_string: str) -> str:
    """The JSON envelope the backend expects around the base64 protobuf."""
    return json.dumps(
        {
            "gateway": "python_webhook",
            "data": upload_string,
            "published_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }
    )


def to_upload_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare one device frame for the backend: one row per whole second, no inf.

    Frames are indexed by unix time in milliseconds (see naneos.frames).
    The index is rounded, not truncated: the devices sample at ~1Hz with a
    phase of their own, so truncating puts the two samples that straddle a
    second boundary into the same second, where one of them wins, and
    leaves the neighbouring second without a row at all.

    The backend takes at most 1 Hz. Rows that land in the same second, as
    they do for a device read at 10 Hz or 100 Hz, are merged into one.
    """
    df = df.replace([float("inf"), -float("inf")], 0)
    df.index = pd.Index(
        np.rint(df.index.to_numpy(dtype="float64") / 1e3).astype("int64"),
        name=df.index.name,
    )
    return aggregate_duplicate_index(df)


def build_combined_entry(data: dict[int, pd.DataFrame], abs_time: int) -> pb.CombinedData:
    """The protobuf message for a snapshot, with timestamps relative to abs_time."""
    devices = [create_proto_device(sn, abs_time, to_upload_frame(df)) for sn, df in data.items()]
    return create_combined_entry(devices=devices, abs_timestamp=abs_time)

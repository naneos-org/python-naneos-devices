"""Upload of gathered snapshots to the naneos IoT service."""

import base64
import datetime
import json
import math
import time

import numpy as np
import pandas as pd
import requests

from naneos.diagnostics import PulseForm, UiCurve
from naneos.frames import aggregate_duplicate_index
from naneos.protobuf import proto_v2_pb2 as pb
from naneos.protobuf.protobuf import (
    POINT_FIELDS,
    create_combined_entry,
    create_proto_device,
    create_pulse_form,
    create_ui_curve,
)

# The v2 API has one endpoint per message type.
BASE_URL = "https://hg3zkburji.execute-api.eu-central-1.amazonaws.com/dev/proto/v2"
URL_COMBINED_DATA = f"{BASE_URL}/combined_data"
URL_UI_CURVE = f"{BASE_URL}/uicurve"
URL_PULSE_FORM = f"{BASE_URL}/pulseform"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}
TIMEOUT_SECONDS = 10
# The backend needs about 2.7 ms per data point (measured: 690 points in 2.2 s, a normal
# 13 point request in 0.35 s), so a request that carries a backlog gets more time. The API
# gateway gives up after 29 s, waiting longer than that is pointless.
TIMEOUT_SECONDS_PER_ROW = 0.005
MAX_TIMEOUT_SECONDS = 30

# The columns of a frame the upload reads: the fields of the wire format and the device type.
UPLOAD_COLUMNS = ("device_type", *dict.fromkeys(field.column for field in POINT_FIELDS))


def prepare_frames(data: dict[int, pd.DataFrame]) -> dict[int, pd.DataFrame]:
    """The frames of a snapshot as the upload needs them, small enough to keep for a day.

    One row per second (see to_upload_frame) and only the columns that have a
    field on the wire and data in them: 21 of the 56 columns of a P2 frame. The
    message built from the result is the message built from the full frame.
    Frames from here can be concatenated and sent with send_frames().
    """
    prepared: dict[int, pd.DataFrame] = {}
    for serial, df in data.items():
        if df.empty:
            continue
        frame = to_upload_frame(df)
        keep = [column for column in UPLOAD_COLUMNS if column in frame.columns]
        prepared[serial] = _compact(frame[keep].dropna(axis=1, how="all"))
    return prepared


def _compact(frame: pd.DataFrame) -> pd.DataFrame:
    """The same values in plain numpy columns: float32 where it was float32, else float64.

    pandas' nullable dtypes (Float32, Int32) give every column a block of its own
    with about 1.4 KB of objects around it, more than 600 s of data of that
    column. Plain columns of one dtype share a block, and a missing value is a NaN.
    """
    if frame.empty:
        return frame
    single = [c for c in frame.columns if str(frame[c].dtype).lower() == "float32"]
    double = [c for c in frame.columns if c not in single]
    parts = []
    for columns, dtype in ((single, "float32"), (double, "float64")):
        if columns:
            values = frame[columns].to_numpy(dtype=dtype, na_value=np.nan)
            parts.append(pd.DataFrame(values, index=frame.index, columns=columns))
    return pd.concat(parts, axis=1)


def send_frames(frames: dict[int, pd.DataFrame]) -> requests.Response:
    """Upload frames from prepare_frames(), keyed by device serial number.

    The frames may hold the rows of several snapshots: the timestamps in the
    message are relative to now, so old data lands at its own time.
    Blocks for up to TIMEOUT_SECONDS, more for a request with many rows. Raises
    requests.RequestException on network problems (requests.ReadTimeout when the
    server was reached but did not answer in time); HTTP errors are reported by
    the returned response.
    """
    # ceil, not int: the rows are rounded to the nearest second (to_upload_frame), so a sample
    # from the second half of the current second lies after int(now), and would get an age of -1.
    abs_time = math.ceil(time.time())
    rows = sum(len(df) for df in frames.values())
    timeout = min(MAX_TIMEOUT_SECONDS, TIMEOUT_SECONDS + TIMEOUT_SECONDS_PER_ROW * rows)
    return _post(URL_COMBINED_DATA, build_prepared_entry(frames, abs_time), timeout)


def upload_snapshot(data: dict[int, pd.DataFrame]) -> requests.Response:
    """Upload the frames of a snapshot, keyed by device serial number.

    Blocks for up to TIMEOUT_SECONDS. Raises requests.RequestException on
    network problems; HTTP errors are reported by the returned response.
    """
    return send_frames(prepare_frames(data))


def upload_ui_curve(curve: UiCurve) -> requests.Response:
    """Upload one UI curve. Blocks and raises like upload_snapshot()."""
    return _post(URL_UI_CURVE, create_ui_curve(curve))


def upload_pulse_form(form: PulseForm) -> requests.Response:
    """Upload one pulse form. Blocks and raises like upload_snapshot()."""
    return _post(URL_PULSE_FORM, create_pulse_form(form))


def upload_diagnostic(diagnostic: UiCurve | PulseForm) -> requests.Response:
    """Upload a UI curve or a pulse form to its endpoint."""
    if isinstance(diagnostic, UiCurve):
        return upload_ui_curve(diagnostic)
    return upload_pulse_form(diagnostic)


def _post(
    url: str,
    message: pb.CombinedData | pb.UiCurve | pb.PulseForm,
    timeout: float = TIMEOUT_SECONDS,
) -> requests.Response:
    payload = base64.b64encode(message.SerializeToString()).decode()
    return requests.post(url, headers=HEADERS, data=build_body(payload), timeout=timeout)


def backend_status(response: requests.Response) -> tuple[int, str]:
    """The status the backend answered with, and what it said (empty if nothing).

    The API gateway can wrap the answer of the lambda: a route the deployed
    lambda does not know comes back as HTTP 200 whose body is
    {"statusCode": 404, "body": ...}. Trusting the HTTP status alone would
    count that upload as done.
    """
    if response.status_code != 200:
        return response.status_code, ""
    try:
        wrapper = response.json()
    except ValueError:
        return 200, ""
    if not isinstance(wrapper, dict) or not isinstance(wrapper.get("statusCode"), int):
        return 200, ""
    return wrapper["statusCode"], str(wrapper.get("body", ""))[:200]


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
    return build_prepared_entry(prepare_frames(data), abs_time)


def build_prepared_entry(frames: dict[int, pd.DataFrame], abs_time: int) -> pb.CombinedData:
    """The message for frames from prepare_frames(); they must not go through it twice."""
    devices = [create_proto_device(sn, abs_time, df) for sn, df in frames.items()]
    return create_combined_entry(devices=devices, abs_timestamp=abs_time)

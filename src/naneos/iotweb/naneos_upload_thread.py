import base64
import datetime
import json
from collections.abc import Callable
from threading import Thread
from typing import ClassVar

import numpy as np
import pandas as pd
import requests

from naneos.frames import aggregate_duplicate_index
from naneos.logger import get_naneos_logger
from naneos.protobuf.protobuf import create_combined_entry, create_proto_device

logger = get_naneos_logger(__name__)


class NaneosUploadThread(Thread):
    URL: ClassVar[str] = "https://hg3zkburji.execute-api.eu-central-1.amazonaws.com/prod/proto/v1"
    HEADERS: ClassVar[dict] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    def __init__(
        self,
        data: dict[int, pd.DataFrame],
        callback: Callable[[bool], None] | None,
    ) -> None:
        """Adding the data that should be uploaded to the database.

        Args:
            data (dict[int, pd.DataFrame]): Data to upload, keyed by device serial number.
            callback (Callable[[bool], None] | None): Called with the upload result.
        """
        super().__init__()
        self.data = data
        self._callback = callback

    def run(self) -> None:
        try:
            ret = self.upload(self.data)

            if self._callback:
                if ret.status_code == 200:
                    self._callback(True)
                else:
                    self._callback(False)
        except Exception as e:
            logger.exception(f"Error in upload: {e}")
            if self._callback:
                self._callback(False)

    @staticmethod
    def get_body(upload_string: str) -> str:
        """The JSON envelope the backend expects around the base64 protobuf."""
        return json.dumps(
            {
                "gateway": "python_webhook",
                "data": upload_string,
                "published_at": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        )

    @staticmethod
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

    @classmethod
    def build_combined_entry(cls, data: dict[int, pd.DataFrame], abs_time: int):
        """The protobuf message for a snapshot, with timestamps relative to abs_time."""
        devices = [
            create_proto_device(sn, abs_time, cls.to_upload_frame(df)) for sn, df in data.items()
        ]
        return create_combined_entry(devices=devices, abs_timestamp=abs_time)

    @classmethod
    def upload(cls, data: dict[int, pd.DataFrame]) -> requests.Response:
        abs_time = int(datetime.datetime.now().timestamp())
        combined_entry = cls.build_combined_entry(data, abs_time)

        proto_str = combined_entry.SerializeToString()
        proto_str_base64 = base64.b64encode(proto_str).decode()

        body = cls.get_body(proto_str_base64)
        r = requests.post(cls.URL, headers=cls.HEADERS, data=body, timeout=10)
        return r

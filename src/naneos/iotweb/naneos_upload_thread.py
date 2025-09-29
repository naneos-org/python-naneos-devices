import base64
import datetime
import pickle
from threading import Thread
from typing import Callable, ClassVar, Optional

import pandas as pd
import requests

from naneos.logger import LEVEL_WARNING, get_naneos_logger
from naneos.protobuf.protobuf import create_combined_entry, create_proto_device

logger = get_naneos_logger(__name__, LEVEL_WARNING)


class NaneosUploadThread(Thread):
    URL: ClassVar[str] = "https://hg3zkburji.execute-api.eu-central-1.amazonaws.com/prod/proto/v1"
    HEADERS: ClassVar[dict] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    def __init__(
        self,
        data: dict[int, pd.DataFrame],
        callback: Optional[Callable[[bool], None]],
    ) -> None:
        """Adding the data that should be uploaded to the database.

        Args:
            data (dict[int, pd.DataFrame]): Data to upload, where the key is the device serial number and the value is a DataFrame.
            callback (Optional[Callable[[bool], None]]): Callback function that is called after upload.
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
                self._callback(False)  # delete data because it was corrupted

    @staticmethod
    def get_body(upload_string: str) -> str:
        return f"""
            {{
                "gateway": "python_webhook",
                "data": "{upload_string}",
                "published_at": "{datetime.datetime.now().isoformat()}"
            }}
            """

    @classmethod
    def upload(cls, data: dict[int, pd.DataFrame]) -> requests.Response:
        abs_time = int(datetime.datetime.now().timestamp())
        devices = []

        for sn, df in data.items():
            # make all inf values in df_p2_pro 0
            df = df.replace([float("inf"), -float("inf")], 0)

            # detect ms timestamp and convert to s
            if df.index[0] > 1e12:
                df.index = df.index / 1e3
                df.index = df.index.astype(int)

            devices.append(create_proto_device(sn, abs_time, df))

        combined_entry = create_combined_entry(devices=devices, abs_timestamp=abs_time)

        proto_str = combined_entry.SerializeToString()
        proto_str_base64 = base64.b64encode(proto_str).decode()

        body = cls.get_body(proto_str_base64)
        r = requests.post(cls.URL, headers=cls.HEADERS, data=body, timeout=10)
        return r


def read_pickle_file(file_path: str) -> dict[int, pd.DataFrame]:
    with open(file_path, "rb") as f:
        data = pickle.load(f)
    return data


if __name__ == "__main__":
    data = read_pickle_file("partector_data.pkl")

    uploader = NaneosUploadThread(
        data, callback=lambda success: print(f"Upload success: {success}")
    )
    uploader.start()
    uploader.join()

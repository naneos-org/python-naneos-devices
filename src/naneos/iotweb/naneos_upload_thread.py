import base64
import datetime
from threading import Thread
from typing import Callable, ClassVar, Optional

import pandas as pd
import requests

from naneos.logger import get_naneos_logger
from naneos.protobuf.protobuf import (
    create_combined_entry,
    create_proto_p1,
    create_proto_p2,
    create_proto_p2_pro,
    create_proto_p2_pro_garage,
)

logger = get_naneos_logger(__name__)


class NaneosUploadThread(Thread):
    URL: ClassVar[str] = "https://hg3zkburji.execute-api.eu-central-1.amazonaws.com/dev/proto/v1"
    HEADERS: ClassVar[dict] = {"Content-Type": "application/json", "Accept": "application/json"}

    def __init__(
        self, data: list[tuple[int, str, pd.DataFrame]], callback: Optional[Callable[[bool], None]]
    ) -> None:
        """Adding the data that should be uploaded to the database.

        Args:
            data (list[tuple[int, pd.DataFrame]]):
                int: serial number
                str: device type
                pd.DataFrame: data to upload
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
            logger.error(f"Error in upload: {e}")
            if self._callback:
                self._callback(True)  # delete data because it was corrupted

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
    def upload(cls, data: list[tuple[int, str, pd.DataFrame]]) -> requests.Response:
        abs_time = int(datetime.datetime.now().timestamp())
        devices = []

        for device in data:
            sn = device[0]
            device_type = device[1]
            df = device[2]

            if device_type == "P1":
                devices.append(create_proto_p1(sn, abs_time, df))
            elif device_type == "P2":
                devices.append(create_proto_p2(sn, abs_time, df))
            elif device_type == "P2_Pro":
                devices.append(create_proto_p2_pro(sn, abs_time, df))
            elif device_type == "P2_Pro_Garage":
                devices.append(create_proto_p2_pro_garage(sn, abs_time, df))
            else:
                raise ValueError(f"Unknown device type: {device_type}")

        combined_entry = create_combined_entry(devices=devices, abs_timestamp=abs_time)

        proto_str = combined_entry.SerializeToString()
        proto_str_base64 = base64.b64encode(proto_str).decode()

        body = cls.get_body(proto_str_base64)
        r = requests.post(cls.URL, headers=cls.HEADERS, data=body, timeout=10)
        # print(f"Status code: {r.status_code} text={r.text}")
        return r


if __name__ == "__main__":
    df_p2: pd.DataFrame = pd.read_pickle(
        "/Users/huegi/gitlocal/naneos/naneos-devices/tests/p2_test_data.pkl"
    )
    df_p2_pro: pd.DataFrame = pd.read_pickle(
        "/Users/huegi/gitlocal/naneos/naneos-devices/tests/p2_pro_test_data.pkl"
    )

    def callback(ret: bool) -> None:
        print(f"Callback: {ret}")

    data = [(int(777), str("P2_Pro"), df_p2_pro), (int(666), str("P2"), df_p2)]  # noqa: UP018
    # NaneosUploadThread.upload(data)

    t = NaneosUploadThread(data, callback)
    t.start()
    t.join()

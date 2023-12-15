import base64
import datetime
from threading import Thread
from typing import Callable, Optional

import pandas as pd
import requests

from naneos.logger import get_naneos_logger
from naneos.protobuf import create_combined_entry, create_partector_2_pro_garagenbox

logger = get_naneos_logger(__name__)


class Partector2ProGarageUpload(Thread):
    URL = "https://hg3zkburji.execute-api.eu-central-1.amazonaws.com/dev/proto/v1"
    HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

    def __init__(
        self, df: pd.DataFrame, serial_number: int, callback: Optional[Callable[[bool], None]]
    ) -> None:
        super().__init__()
        self.df = df
        self.serial_number = serial_number
        self._callback = callback

    def run(self) -> None:
        try:
            ret = self.upload(self.df, self.serial_number)

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

    # can be used directly then its not threaded
    @classmethod
    def upload(cls, df: pd.DataFrame, serial_number: int) -> requests.Response:
        abs_time = int(datetime.datetime.now().timestamp())
        device = create_partector_2_pro_garagenbox(df, serial_number, abs_time)
        combined_entry = create_combined_entry(devices=[device], abs_timestamp=abs_time)

        proto_str = combined_entry.SerializeToString()
        # .decode() converts to str
        proto_str_base64 = base64.b64encode(proto_str).decode()

        body = cls.get_body(proto_str_base64)
        r = requests.post(cls.URL, headers=cls.HEADERS, data=body, timeout=10)
        # print(f"Status code: {r.status_code} text={r.text}")
        return r


if __name__ == "__main__":
    df = pd.read_pickle("/Users/huegi/gitlocal/naneos/naneos-devices/tests/df_garagae.pkl")

    abs_time = int(datetime.datetime.now().timestamp())
    serial_number = 777
    Partector2ProGarageUpload.upload(df, serial_number)

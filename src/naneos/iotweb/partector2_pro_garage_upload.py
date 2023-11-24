import base64
import datetime
from threading import Thread

import pandas as pd
import requests

from naneos.protobuf import create_Combined_entry, create_partector_2_pro_garagenbox


class Partector2ProGarageUpload(Thread):
    URL = "https://hg3zkburji.execute-api.eu-central-1.amazonaws.com/dev/proto/v1"
    HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

    def __init__(self, df: pd.DataFrame, serial_number: int, callback: callable):
        super().__init__()
        self.df = df
        self.serial_number = serial_number
        self._callback = callback

    def run(self):
        ret = self.upload(self.df, self.serial_number)

        if self._callback:
            if ret.status_code == 200:
                self._callback(True)
            else:
                self._callback(False)

    @staticmethod
    def get_body(upload_string) -> str:
        return f"""
            {{
                "gateway": "python_webhook",
                "data": "{upload_string}",
                "published_at": "{datetime.datetime.now().isoformat()}"
            }}
            """

    # can be used directly then its not threaded
    @classmethod
    def upload(cls, df: pd.DataFrame, serial_number: int):
        abs_time = int(datetime.datetime.now().timestamp())
        device = create_partector_2_pro_garagenbox(df, serial_number, abs_time)
        combined_entry = create_Combined_entry(devices=[device], abs_time=abs_time)

        proto_str = combined_entry.SerializeToString()
        # .decode() converts to str
        proto_str_base64 = base64.b64encode(proto_str).decode()

        body = cls.get_body(proto_str_base64)
        r = requests.post(cls.URL, headers=cls.HEADERS, data=body, timeout=10)
        # print(f"Status code: {r.status_code} text={r.text}")
        return r


if __name__ == "__main__":
    df = pd.read_pickle(
        "/Users/huegi/Code/naneos/python/python-naneos-devices/tests/df_garagae.pkl"
    )

    abs_time = int(datetime.datetime.now().timestamp())
    serial_number = 8224
    Partector2ProGarageUpload.upload(df, serial_number)
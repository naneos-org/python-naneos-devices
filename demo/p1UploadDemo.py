import base64
import datetime
import time

import pandas as pd
import requests

from naneos.partector.partector1 import Partector1
from naneos.partector.scan_for_partector import scan_for_serial_partectors
from naneos.protobuf.protobuf import create_Combined_entry, create_Partector1_entry


def main():
    devs = scan_for_serial_partectors()
    devs = devs["P1"]

    p1 = Partector1(list(devs.values())[0])

    # every 5 seconds interuptable by keyboard
    while True:
        try:
            time.sleep(20)
            df1 = p1.get_data_pandas()

            abs_time = int(datetime.datetime.now().timestamp())
            p1_device = create_Partector1_entry(df1, p1._serial_number, abs_time)
            devices = [p1_device]

            combined = create_Combined_entry(devices=devices, abs_time=abs_time)

            proto_string = combined.SerializeToString()
            proto_string_base64 = base64.b64encode(proto_string)
            print(proto_string_base64)

            # send this string to the server
            url = "https://hg3zkburji.execute-api.eu-central-1.amazonaws.com/prod/proto/v1"
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            body = f"""
                    {{
                        "gateway": "python_webhook",
                        "data": "{proto_string_base64.decode()}",
                        "published_at": "{datetime.datetime.now().isoformat()}"
                    }}
                    """

            print(body)

            # send the data to the server
            r = requests.post(url, headers=headers, data=body)
            print(r.status_code)
            print(r.text)

        except KeyboardInterrupt:
            break

    p1.close()


if __name__ == "__main__":
    main()

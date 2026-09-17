"""Download data of one device from the naneos IoT service (InfluxDB).

Usage: IOT_GUEST_TOKEN=... python download_iotweb.py <bucket> <serial_number> <start> <stop>
with start / stop as YYYY-MM-DD. Ask naneos for a read token.
"""

import datetime as dt
import os
import sys

from naneos.iotweb.download import download_from_iotweb


def main() -> None:
    token = os.getenv("IOT_GUEST_TOKEN")
    if token is None:
        sys.exit("Set IOT_GUEST_TOKEN in your environment.")
    if len(sys.argv) != 5:
        sys.exit(__doc__)

    bucket, serial_number, start, stop = sys.argv[1:]
    df = download_from_iotweb(
        bucket,
        serial_number,
        dt.datetime.fromisoformat(start),
        dt.datetime.fromisoformat(stop),
        token,
    )
    print(df)


if __name__ == "__main__":
    main()

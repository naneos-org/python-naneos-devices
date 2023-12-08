from naneos.iotweb import download_from_iotweb


def test_download_8134() -> None:
    import datetime as dt
    import os

    import pandas as pd

    token: str | None = os.getenv("IOT_GUEST_TOKEN", None)
    if token is None:
        raise ValueError("No token found in your environment")

    # use local timezone for start
    start = dt.datetime(2023, 11, 26)
    stop = dt.datetime(2023, 11, 27)
    serial_number = "8134"
    name = "iot_guest"

    df: pd.DataFrame = download_from_iotweb(name, serial_number, start, stop, token)
    assert df.shape[0] > 0

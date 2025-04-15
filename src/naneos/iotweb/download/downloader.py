import datetime as dt

import pandas as pd
from influxdb_client.client.influxdb_client import InfluxDBClient

from naneos.logger import get_naneos_logger

URL_INFLUX = "https://influxdb.naneos.ch"
ORG_INFLUX = "naneos"

logger = get_naneos_logger(__name__)


def get_query(bucket: str, serial_number: str, start: str, stop: str) -> str:
    query = f"""
        from(bucket: "{bucket}")
        |> range(start: {start}, stop: {stop})
        |> filter(fn: (r) => r["_measurement"] == "v6_sensor")
        |> filter(fn: (r) => r["serial_number"] == "{serial_number}")
        |> keep(columns: ["_time", "_value", "_field"])
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    """

    return query


def create_start_stop_timestamp(start_dt: dt.datetime, stop_dt: dt.datetime) -> list:
    """Returns a list of lists with start stop times in 1 day chunks in unix timesamps"""
    delta_seconds = 3600 * 24 * 2

    start = int(start_dt.timestamp())
    stop = int(stop_dt.timestamp())

    start_stop_times = []

    while start < stop - delta_seconds:
        start_stop_times.append([start, start + delta_seconds])
        start += delta_seconds
    start_stop_times.append([start, stop])

    return start_stop_times


def download_from_iotweb(
    name: str, serial_number: str, start: dt.datetime, stop: dt.datetime, token: str
) -> pd.DataFrame:
    """Download your data from influxdb.naneos.ch.
    1 Month of data takes about 30 seconds to download and uses about 100 MB of data.

    You need to have a token to access the data.
    Ask mario.huegi@naneos.ch for your read token.
    We kindly ask you to not overuse our server.
    If you need to download the same data in a recuring pattern, contact us.

    Args:
        name (str): Name of the influx bucket.
        serial_number (str): Serial number of your device as string.
        start (dt.datetime): Start date of the data you want to download.
        stop (dt.datetime): End date of the data you want to download.
        token (str): Your read token. Do not push your token to public repositories.

    Returns:
        pd.DataFrame: Dataframe with your data.
    """
    timestamps = create_start_stop_timestamp(start, stop)

    dfs = []

    with InfluxDBClient(url=URL_INFLUX, org=ORG_INFLUX, token=token) as client:
        for t1, t2 in timestamps:
            query = get_query(name, serial_number, t1, t2)

            df = client.query_api().query_data_frame(query)

            if isinstance(df, list):
                dfs.extend(df)
            elif isinstance(df, pd.DataFrame):
                dfs.append(df)
            else:
                logger.warning(f"Unknown type: {type(df)}")

    df = pd.concat(dfs, axis=0)
    df.set_index("_time", inplace=True)
    df.drop(["result", "table"], axis=1, inplace=True)

    return df


if __name__ == "__main__":
    import os

    token = os.getenv("IOT_GUEST_TOKEN", None)
    if token is None:
        raise ValueError("No token found in your environment")

    start = dt.datetime(2023, 11, 25)
    stop = dt.datetime(2023, 11, 27)
    serial_number = "8134"
    name = "iot_guest"

    df = download_from_iotweb(name, serial_number, start, stop, token)
    print(df)

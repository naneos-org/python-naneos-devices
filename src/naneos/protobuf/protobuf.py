import base64
import datetime

import google.protobuf.json_format as pbJson
import google.protobuf.message as pbMessage
import pandas as pd

import naneos.protobuf.protoV1_pb2 as pbScheme


def create_Combined_entry(
    devices=None,
    abs_time=None,
    gateway_points=None,
    position_points=None,
    wind_points=None,
):
    if devices is None:
        raise ValueError("Devices must be given!")
    if not isinstance(devices, list):
        raise ValueError("Devices must be a list!")

    combined = pbScheme.CombinedData()
    combined.abs_timestamp = abs_time

    for device in devices:
        combined.devices.append(device)

    if gateway_points is not None:
        combined.gateway_points.extend(gateway_points)

    if position_points is not None:
        combined.position_points.extend(position_points)

    if wind_points is not None:
        combined.wind_points.extend(wind_points)

    return combined


def create_Partector1_entry(
    df: pd.DataFrame, serial_number: int = None, abs_time: int = None
):
    if serial_number is None:
        raise ValueError("Serial number must be given!")
    if abs_time is None:
        raise ValueError("Absolute time must be given!")

    device = pbScheme.Device()

    device.type = 0  # Partector1
    device.serial_number = serial_number

    for _, row in df.iterrows():
        device_point = pbScheme.DevicePoint()

        device_point.timestamp = abs_time - int(row.name.timestamp())
        device_point.device_status = int(row["device_status"])

        device_point.ldsa = int(row["LDSA"] * 100.0)
        device_point.battery_voltage = int(row["batt_voltage"] * 100.0)

        idiff_tmp = row["idiff_global"] if row["idiff_global"] > 0 else 0
        device_point.diffusion_current = int(idiff_tmp * 100.0)
        device_point.corona_voltage = int(row["ucor_global"])
        device_point.flow = int(row["flow"] * 1000.0)
        device_point.temperature = int(row["T"])
        device_point.relative_humidity = int(row["RHcorr"])

        device.device_points.append(device_point)

    return device


if __name__ == "__main__":
    df = pd.read_pickle("p1.pkl")

    abs_time = int(datetime.datetime.now().timestamp())

    device_list = []

    device_list.append(create_Partector1_entry(df, 16, abs_time))

    combined = create_Combined_entry(devices=device_list, abs_time=abs_time)

    json_string = pbJson.MessageToJson(combined, including_default_value_fields=True)
    proto_string = combined.SerializeToString()

    # print(json_string)
    # print(proto_string)

    # base64 encode proto_string
    base64_string = base64.b64encode(proto_string)

    print(base64_string)

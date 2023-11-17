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


def create_partector_2_pro_garagenbox(
    df: pd.DataFrame, serial_number: int = None, abs_time: int = None
):
    if serial_number is None:
        raise ValueError("Serial number must be given!")
    if abs_time is None:
        raise ValueError("Absolute time must be given!")
    if len(df) == 0:
        raise ValueError("Dataframe must not be empty!")

    device = pbScheme.Device()  # contains type, serial_number, device_points
    device.type = 0  # Partector1/2 #TODO: ask @rschre what he wants for special devices
    device.serial_number = serial_number

    # TODO: check if using the right axis
    devicePoints = df.apply(_create_device_Point, axis=1, abs_time=abs_time).to_list()

    device.device_points.extend(devicePoints)

    return device


def _create_device_Point(ser: pd.Series, abs_time: int) -> pbScheme.DevicePoint:
    device_point = pbScheme.DevicePoint()

    # mandatory fields
    device_point.timestamp = abs_time - int(ser.name.timestamp())
    device_point.device_status = int(ser["device_status"])

    # optional fields
    device_point.particle_number_concentration = int(ser["number"])
    device_point.average_particle_diameter = int(ser["diameter"])
    device_point.ldsa = int(ser["LDSA"] * 100.0)
    device_point.surface = int(ser["surface"] * 100.0)
    device_point.particle_mass = int(ser["particle_mass"] * 100.0)
    device_point.sigma_size_dist = int(ser["sigma"] * 100.0)
    idiff_tmp = ser["idiff_global"] if ser["idiff_global"] > 0 else 0
    device_point.diffusion_current = int(idiff_tmp * 100.0)
    device_point.corona_voltage = int(ser["ucor_global"])
    device_point.deposition_voltage = int(ser["deposition_voltage"])
    device_point.temperature = int(ser["T"])
    device_point.relative_humidity = int(ser["RHcorr"])
    device_point.ambient_pressure = int(ser["P_average"] * 10.0)
    device_point.flow = int(ser["flow_from_dp"] * 1000.0)
    device_point.battery_voltage = int(ser["batt_voltage"] * 100.0)
    device_point.pump_current = int(ser["pump_current"] * 100.0)
    device_point.pump_pwm = int(ser["pump_pwm"])

    # pro stuff
    device_point.cs_status = int(ser["cs_status"])
    device_point.steps_inversion = int(ser["steps"])
    device_point.current_dist_0 = int(ser["current_0"])
    device_point.current_dist_1 = int(ser["current_1"])
    device_point.current_dist_2 = int(ser["current_2"])
    device_point.current_dist_3 = int(ser["current_3"])
    device_point.current_dist_4 = int(ser["current_4"])
    device_point.particle_number_10nm = int(ser["particle_number_10nm"])
    device_point.particle_number_16nm = int(ser["particle_number_16nm"])
    device_point.particle_number_26nm = int(ser["particle_number_26nm"])
    device_point.particle_number_43nm = int(ser["particle_number_43nm"])
    device_point.particle_number_70nm = int(ser["particle_number_70nm"])
    device_point.particle_number_114nm = int(ser["particle_number_114nm"])
    device_point.particle_number_185nm = int(ser["particle_number_185nm"])
    device_point.particle_number_300nm = int(ser["particle_number_300nm"])

    return device_point


if __name__ == "__main__":
    df = pd.read_pickle(
        "/Users/huegi/Code/naneos/python/python-naneos-devices/tests/df_garagae.pkl"
    )

    abs_time = int(datetime.datetime.now().timestamp())
    serial_number = 777
    create_partector_2_pro_garagenbox(df, serial_number, abs_time)

    # df = pd.read_pickle("p1.pkl")

    # abs_time = int(datetime.datetime.now().timestamp())

    # device_list = []

    # device_list.append(create_Partector1_entry(df, 16, abs_time))

    # combined = create_Combined_entry(devices=device_list, abs_time=abs_time)

    # json_string = pbJson.MessageToJson(combined, including_default_value_fields=True)
    # proto_string = combined.SerializeToString()

    # # print(json_string)
    # # print(proto_string)

    # # base64 encode proto_string
    # base64_string = base64.b64encode(proto_string)

    # print(base64_string)

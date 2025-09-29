from typing import Optional

import pandas as pd

import naneos.protobuf.protoV1_pb2 as pbScheme
from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint


def create_combined_entry(
    devices: list[pbScheme.Device],
    abs_timestamp: int,
    gateway_points: Optional[list[pbScheme.GatewayPointLegacy]] = None,
    position_points: Optional[list[pbScheme.PositionPoint]] = None,
    wind_points: Optional[list[pbScheme.WindPoint]] = None,
) -> pbScheme.CombinedData:
    combined = pbScheme.CombinedData()
    combined.abs_timestamp = abs_timestamp

    combined.devices.extend(devices)

    if gateway_points is not None:
        combined.gateway_points_legacy.extend(gateway_points)

    if position_points is not None:
        combined.position_points.extend(position_points)

    if wind_points is not None:
        combined.wind_points.extend(wind_points)

    return combined


def create_proto_device(sn: int, abs_time: int, df: pd.DataFrame) -> pbScheme.Device:
    device = pbScheme.Device()
    device.type = (
        int(df["device_type"].iloc[-1])
        if "device_type" in df
        else NaneosDeviceDataPoint.DEV_TYPE_P2
    )
    device.serial_number = sn

    device_points = df.apply(_create_device_point, axis=1, abs_time=abs_time).to_list()  # type: ignore
    device_points = [x for x in device_points if x is not None]

    device.device_points.extend(device_points)

    return device


def _create_device_point(ser: pd.Series, abs_time: int) -> Optional[pbScheme.DevicePoint]:
    try:
        device_point = pbScheme.DevicePoint()

        ser = ser.dropna()

        # mandatory fields
        if isinstance(ser.name, int):
            timestamp = ser.name
        else:
            raise ValueError("Timestamp is not an int!")
        device_point.timestamp = abs_time - timestamp
        if "device_status" in ser:
            device_point.device_status = int(ser["device_status"])
        if "firmware_version" in ser:
            device_point.firmware_version = int(ser["firmware_version"])

        if "ldsa" in ser:
            device_point.ldsa = int(ser["ldsa"] * 100.0)
        if "particle_number_concentration" in ser:
            device_point.particle_number_concentration = int(
                round(ser["particle_number_concentration"])
            )
        if "average_particle_diameter" in ser:
            device_point.average_particle_diameter = int(round(ser["average_particle_diameter"]))
        if "particle_mass" in ser:
            device_point.particle_mass = int(round(ser["particle_mass"] * 100.0))
        if "particle_surface" in ser:
            device_point.particle_surface = int(round(ser["particle_surface"] * 100.0))
        if "diffusion_current" in ser:
            idiff_tmp = ser["diffusion_current"] if ser["diffusion_current"] > 0 else 0
            device_point.diffusion_current = int(round(idiff_tmp * 100.0))
        if "diffusion_current_offset" in ser:
            device_point.diffusion_current_offset = int(
                round(ser["diffusion_current_offset"] * 100.0)
            )
        if "diffusion_current_stddev" in ser:
            device_point.diffusion_current_stddev = int(
                round(ser["diffusion_current_stddev"] * 100.0)
            )
        # TODO: implement in protobuf
        # if "diffusion_current_average" in ser:
        #     device_point.diffusion_current_average = int(
        #         round(ser["diffusion_current_average"] * 100.0)
        #     )
        # if "diffusion_current_max" in ser:
        #     device_point.diffusion_current_max = int(round(ser["diffusion_current_max"] * 100.0))
        if "diffusion_current_delay_on" in ser:
            delay_on_tmp = max(ser["diffusion_current_delay_on"], 0)
            device_point.diffusion_current_delay_on = int(round(delay_on_tmp))
        if "diffusion_current_delay_off" in ser:
            delay_off_tmp = max(ser["diffusion_current_delay_off"], 0)
            device_point.diffusion_current_delay_off = int(round(delay_off_tmp))
        if "corona_voltage" in ser:
            device_point.corona_voltage = int(round(ser["corona_voltage"]))
        # TODO: implement in protobuf
        # if "corona_voltage_onset" in ser:
        #     device_point.corona_voltage_onset = int(round(ser["corona_voltage_onset"]))
        if "electrometer_1_amplitude" in ser:
            device_point.electrometer_1_offset = int(round(ser["electrometer_1_amplitude"] * 10.0))
        if "electrometer_2_amplitude" in ser:
            device_point.electrometer_2_offset = int(round(ser["electrometer_2_amplitude"] * 10.0))
        if "electrometer_1_gain" in ser:
            device_point.electrometer_1_gain = int(round(ser["electrometer_1_gain"] * 100.0))
        if "electrometer_2_gain" in ser:
            device_point.electrometer_2_gain = int(round(ser["electrometer_2_gain"] * 100.0))
        if "temperature" in ser:
            device_point.temperature = int(round(ser["temperature"]))
        if "relative_humidity" in ser:
            device_point.relative_humidity = int(round(ser["relative_humidity"]))
        if "flow_from_dp" in ser:
            device_point.flow = int(round(ser["flow_from_dp"] * 1000.0))
        if "deposition_voltage" in ser:
            device_point.deposition_voltage = int(round(ser["deposition_voltage"]))
        if "battery_voltage" in ser:
            device_point.battery_voltage = int(round(ser["battery_voltage"] * 100.0))
        if "ambient_pressure" in ser:
            device_point.ambient_pressure = int(round(ser["ambient_pressure"] * 10.0))
        if "channel_pressure" in ser:
            device_point.channel_pressure = int(round(ser["channel_pressure"] * 10.0))
        if "differential_pressure" in ser:
            device_point.differential_pressure = int(round(ser["differential_pressure"] * 10.0))
        if "pump_voltage" in ser:
            device_point.pump_voltage = int(round(ser["pump_voltage"] * 100.0))
        if "pump_current" in ser:
            device_point.pump_current = int(round(ser["pump_current"] * 1000.0))
        if "pump_pwm" in ser:
            device_point.pump_pwm = int(round(ser["pump_pwm"]))
        if "particle_number_10nm" in ser:
            device_point.particle_number_10nm = int(round(ser["particle_number_10nm"]))
        if "particle_number_16nm" in ser:
            device_point.particle_number_16nm = int(round(ser["particle_number_16nm"]))
        if "particle_number_26nm" in ser:
            device_point.particle_number_26nm = int(round(ser["particle_number_26nm"]))
        if "particle_number_43nm" in ser:
            device_point.particle_number_43nm = int(round(ser["particle_number_43nm"]))
        if "particle_number_70nm" in ser:
            device_point.particle_number_70nm = int(round(ser["particle_number_70nm"]))
        if "particle_number_114nm" in ser:
            device_point.particle_number_114nm = int(round(ser["particle_number_114nm"]))
        if "particle_number_185nm" in ser:
            device_point.particle_number_185nm = int(round(ser["particle_number_185nm"]))
        if "particle_number_300nm" in ser:
            device_point.particle_number_300nm = int(round(ser["particle_number_300nm"]))
        if "sigma_size_dist" in ser:
            device_point.sigma_size_dist = int(round(ser["sigma_size_dist"] * 100.0))
        if "steps_inversion" in ser:
            device_point.steps_inversion = int(round(ser["steps_inversion"]))
        if "current_dist_0" in ser:
            device_point.current_dist_0 = int(round(ser["current_dist_0"] * 100000.0))
        if "current_dist_1" in ser:
            device_point.current_dist_1 = int(round(ser["current_dist_1"] * 100000.0))
        if "current_dist_2" in ser:
            device_point.current_dist_2 = int(round(ser["current_dist_2"] * 100000.0))
        if "current_dist_3" in ser:
            device_point.current_dist_3 = int(round(ser["current_dist_3"] * 100000.0))
        if "current_dist_4" in ser:
            device_point.current_dist_4 = int(round(ser["current_dist_4"] * 100000.0))

        if "supply_voltage_5V" in ser:
            device_point.supply_voltage_5V = int(round(ser["supply_voltage_5V"] * 10.0))
        if "positive_voltage_3V3" in ser:
            device_point.positive_voltage_3V3 = int(round(ser["positive_voltage_3V3"] * 10.0))
        if "negative_voltage_3V3" in ser:
            device_point.negative_voltage_3V3 = int(round(ser["negative_voltage_3V3"] * 10.0))
        if " usb_cc_voltage" in ser:
            device_point.usb_cc_voltage = int(round(ser[" usb_cc_voltage"] * 10.0))

        # Needed for the garagenbox
        if "cs_status" in ser:
            device_point.cs_status = int(ser["cs_status"])

    except Exception as e:
        print(f"Error in _create_device_Point: {e}")
        return None

    return device_point

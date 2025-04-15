import base64
import datetime
import time
from typing import Optional

from numpy import isin
import pandas as pd

import naneos.protobuf.protoV1_pb2 as pbScheme


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


def create_proto_p1(sn: int, abs_time: int, df: pd.DataFrame) -> pbScheme.Device:
    device = pbScheme.Device()
    device.type = 1
    device.serial_number = sn

    device_points = df.apply(_create_device_point, axis=1, abs_time=abs_time).to_list()  # type: ignore
    device_points = [x for x in device_points if x is not None]

    device.device_points.extend(device_points)

    return device


def create_proto_p2(sn: int, abs_time: int, df: pd.DataFrame) -> pbScheme.Device:
    device = pbScheme.Device()
    device.type = 0
    device.serial_number = sn

    device_points = df.apply(_create_device_point, axis=1, abs_time=abs_time).to_list()  # type: ignore
    device_points = [x for x in device_points if x is not None]

    device.device_points.extend(device_points)

    return device


def create_proto_p2_pro(sn: int, abs_time: int, df: pd.DataFrame) -> pbScheme.Device:
    device = pbScheme.Device()
    device.type = 2
    device.serial_number = sn

    device_points = df.apply(_create_device_point, axis=1, abs_time=abs_time).to_list()  # type: ignore
    device_points = [x for x in device_points if x is not None]

    device.device_points.extend(device_points)

    return device


def create_proto_p2_pro_cs(sn: int, abs_time: int, df: pd.DataFrame) -> pbScheme.Device:
    device = pbScheme.Device()
    device.type = 3
    device.serial_number = sn

    device_points = df.apply(_create_device_point, axis=1, abs_time=abs_time).to_list()  # type: ignore
    device_points = [x for x in device_points if x is not None]

    device.device_points.extend(device_points)

    return device


def _create_device_point(
    ser: pd.Series, abs_time: int
) -> Optional[pbScheme.DevicePoint]:
    try:
        device_point = pbScheme.DevicePoint()

        ser = ser.dropna()

        # mandatory fields
        if isinstance(ser.name, int):
            timestamp = ser.name
        else:
            raise ValueError("Timestamp is not an int!")
        device_point.timestamp = abs_time - timestamp
        device_point.device_status = int(ser["device_status"])

        # optional fields
        if "idiff_global" in ser:
            idiff_tmp = ser["idiff_global"] if ser["idiff_global"] > 0 else 0
            device_point.diffusion_current = int(idiff_tmp * 100.0)
        elif "diffusion_current" in ser:
            idiff_tmp = ser["diffusion_current"] if ser["diffusion_current"] > 0 else 0
            device_point.diffusion_current = int(idiff_tmp * 100.0)
        if "diffusion_current_offset" in ser:
            device_point.diffusion_current_offset = int(
                ser["diffusion_current_offset"] * 100.0
            )
        if "ucor_global" in ser:
            device_point.corona_voltage = int(ser["ucor_global"])
        elif "corona_voltage" in ser:
            device_point.corona_voltage = int(ser["corona_voltage"])
        if "hiresADC1" in ser:  # hires_adc1
            pass
        if "hiresADC2" in ser:  # hires_adc2
            pass
        if "EM_amplitude1" in ser:  # em_amplitude1
            pass
        if "EM_amplitude2" in ser:  # em_amplitude2
            pass
        if "T" in ser:
            device_point.temperature = int(ser["T"])
        elif "temperature" in ser:
            device_point.temperature = int(ser["temperature"])
        if "RHcorr" in ser:
            device_point.relative_humidity = int(ser["RHcorr"])
        elif "relativ_humidity" in ser:
            device_point.relative_humidity = int(ser["relativ_humidity"])
        if "deposition_voltage" in ser:
            device_point.deposition_voltage = int(ser["deposition_voltage"])
        if "batt_voltage" in ser:
            device_point.battery_voltage = int(ser["batt_voltage"] * 100.0)
        elif "battery_voltage" in ser:
            device_point.battery_voltage = int(ser["battery_voltage"] * 100.0)
        if "flow_from_dp" in ser:
            device_point.flow = int(ser["flow_from_dp"] * 1000.0)
        if "LDSA" in ser:
            device_point.ldsa = int(ser["LDSA"] * 100.0)
        elif "ldsa" in ser:
            device_point.ldsa = int(ser["ldsa"] * 100.0)
        if "diameter" in ser:
            device_point.average_particle_diameter = int(ser["diameter"])
        elif "particle_diameter" in ser:
            device_point.average_particle_diameter = int(ser["particle_diameter"])
        if "number" in ser:
            device_point.particle_number_concentration = int(ser["number"])
        elif "particle_number" in ser:
            device_point.particle_number_concentration = int(ser["particle_number"])
        if "dP" in ser:  # differential_pressure
            pass
        if "P_average" in ser:
            device_point.ambient_pressure = int(ser["P_average"] * 10.0)
        elif "ambient_pressure" in ser:
            device_point.ambient_pressure = int(ser["ambient_pressure"] * 10.0)
        if "em_gain1" in ser:  # multiplicator ???
            device_point.electrometer_gain = int(ser["em_gain1"] * 100.0)
        if "em_gain2" in ser:
            device_point.electrometer_2_gain = int(ser["em_gain2"] * 100.0)

        # P2 Pro
        if "surface" in ser:
            device_point.surface = int(ser["surface"] * 100.0)
        elif "particle_surface" in ser:
            device_point.surface = int(ser["particle_surface"] * 100.0)
        if "particle_mass" in ser:
            device_point.particle_mass = int(ser["particle_mass"] * 100.0)
        if "sigma" in ser:
            device_point.sigma_size_dist = int(ser["sigma"] * 100.0)
        if "pump_current" in ser:
            device_point.pump_current = int(ser["pump_current"] * 1000.0)
        if "pump_pwm" in ser:
            device_point.pump_pwm = int(ser["pump_pwm"])
        if "steps" in ser:
            device_point.steps_inversion = int(ser["steps"])
        elif "dist_steps" in ser:
            device_point.steps_inversion = int(ser["dist_steps"])
        if "current_0" in ser:
            device_point.current_dist_0 = int(ser["current_0"] * 100000.0)
        elif "dist_current_0" in ser:
            device_point.current_dist_0 = int(ser["dist_current_0"])
        if "current_1" in ser:
            device_point.current_dist_1 = int(ser["current_1"] * 100000.0)
        elif "dist_current_1" in ser:
            device_point.current_dist_1 = int(ser["dist_current_1"])
        if "current_2" in ser:
            device_point.current_dist_2 = int(ser["current_2"] * 100000.0)
        elif "dist_current_2" in ser:
            device_point.current_dist_2 = int(ser["dist_current_2"])
        if "current_3" in ser:
            device_point.current_dist_3 = int(ser["current_3"] * 100000.0)
        elif "dist_current_3" in ser:
            device_point.current_dist_3 = int(ser["dist_current_3"])
        if "current_4" in ser:
            device_point.current_dist_4 = int(ser["current_4"] * 100000.0)
        elif "dist_current_4" in ser:
            device_point.current_dist_4 = int(ser["dist_current_4"])
        if "particle_number_10nm" in ser:
            device_point.particle_number_10nm = int(ser["particle_number_10nm"])
        elif "dist_particle_number_10nm" in ser:
            device_point.particle_number_10nm = int(ser["dist_particle_number_10nm"])
        if "particle_number_16nm" in ser:
            device_point.particle_number_16nm = int(ser["particle_number_16nm"])
        elif "dist_particle_number_16nm" in ser:
            device_point.particle_number_16nm = int(ser["dist_particle_number_16nm"])
        if "particle_number_26nm" in ser:
            device_point.particle_number_26nm = int(ser["particle_number_26nm"])
        elif "dist_particle_number_26nm" in ser:
            device_point.particle_number_26nm = int(ser["dist_particle_number_26nm"])
        if "particle_number_43nm" in ser:
            device_point.particle_number_43nm = int(ser["particle_number_43nm"])
        elif "dist_particle_number_43nm" in ser:
            device_point.particle_number_43nm = int(ser["dist_particle_number_43nm"])
        if "particle_number_70nm" in ser:
            device_point.particle_number_70nm = int(ser["particle_number_70nm"])
        elif "dist_particle_number_70nm" in ser:
            device_point.particle_number_70nm = int(ser["dist_particle_number_70nm"])
        if "particle_number_114nm" in ser:
            device_point.particle_number_114nm = int(ser["particle_number_114nm"])
        elif "dist_particle_number_114nm" in ser:
            device_point.particle_number_114nm = int(ser["dist_particle_number_114nm"])
        if "particle_number_185nm" in ser:
            device_point.particle_number_185nm = int(ser["particle_number_185nm"])
        elif "dist_particle_number_185nm" in ser:
            device_point.particle_number_185nm = int(ser["dist_particle_number_185nm"])
        if "particle_number_300nm" in ser:
            device_point.particle_number_300nm = int(ser["particle_number_300nm"])
        elif "dist_particle_number_300nm" in ser:
            device_point.particle_number_300nm = int(ser["dist_particle_number_300nm"])

        # P2 Pro Garage
        if "cs_status" in ser:
            device_point.cs_status = int(ser["cs_status"])

    except Exception as e:
        print(f"Error in _create_device_Point: {e}")
        return None

    return device_point

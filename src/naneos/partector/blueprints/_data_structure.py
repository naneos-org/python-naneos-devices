from dataclasses import dataclass
from typing import Optional, Union

import pandas as pd


def add_to_existing_naneos_data(
    data: dict[int, pd.DataFrame], new_data: dict[int, pd.DataFrame]
) -> dict[int, pd.DataFrame]:
    """
    Adds new data to existing data, merging DataFrames by index.
    If a serial number already exists, it merges the new DataFrame with the existing one.
    """
    for serial, df in list(new_data.items()):
        if serial in data:
            data[serial] = pd.concat([data[serial], df], ignore_index=False)
        else:
            data[serial] = df

    return data


def sort_and_clean_naneos_data(data: dict[int, pd.DataFrame]) -> dict[int, pd.DataFrame]:
    """
    Takes the best connection type for each serial number.
    If there are multiple connection types, it keeps the one with the highest priority:
    - "serial" > "connected" > "advertisement"
    """
    data_return = {}

    for serial, df in data.items():
        if serial is None or df.empty:
            continue

        if "connection_type" in df.columns:
            if (df["connection_type"] == "serial").any():
                df = df[df["connection_type"] == "serial"]
            elif (df["connection_type"] == "connected").any():
                df = df[df["connection_type"] == "connected"]
            elif (df["connection_type"] == "advertisement").any():
                df = df[df["connection_type"] == "advertisement"]

        df = df.sort_index()  # sort by unix_timestamp

        df = df[~df.index.duplicated(keep="last")]

        # if there are rows with device type 2 and 0 remove all 0 rows
        if "device_type" in df.columns:
            if (df["device_type"] == 0).any() and (df["device_type"] == 2).any():
                df = df[df["device_type"] != 0]

        data_return[serial] = df

    return data_return


@dataclass
class NaneosDeviceDataPoint:
    DEV_TYPE_P2 = 0
    DEV_TYPE_P1 = 1
    DEV_TYPE_P2PRO = 2
    DEV_TYPE_P2PRO_CS = 3

    CONN_TYPE_SERIAL = "serial"
    CONN_TYPE_CONNECTED = "connected"
    CONN_TYPE_ADVERTISEMENT = "advertisement"

    BLE_STD_FIELD_NAMES = {
        "serial_number",
        "ldsa",
        "average_particle_diameter",
        "particle_number_concentration",
        "temperature",
        "relative_humidity",
        "device_status",
        "battery_voltage",
        "particle_mass",
    }
    BLE_AUX_FIELD_NAMES = {
        "corona_voltage",
        "diffusion_current",
        "deposition_voltage",
        "flow_from_dp",
        "ambient_pressure",
        "electrometer_1_amplitude",
        "electrometer_2_amplitude",
        "electrometer_1_gain",
        "electrometer_2_gain",
        "diffusion_current_offset",
    }
    BLE_SIZE_DIST_FIELD_NAMES = {
        "particle_number_10nm",
        "particle_number_16nm",
        "particle_number_26nm",
        "particle_number_43nm",
        "particle_number_70nm",
        "particle_number_114nm",
        "particle_number_185nm",
        "particle_number_300nm",
    }

    @staticmethod
    def add_data_point_to_dict(
        devices: dict, data: "NaneosDeviceDataPoint"
    ) -> dict[int, pd.DataFrame]:
        if data.serial_number not in devices:
            devices[data.serial_number] = pd.DataFrame()

        if len(devices[data.serial_number]) > 300:  # remove oldest rows if more than 300 rows
            devices[data.serial_number].drop(devices[data.serial_number].index[0], inplace=True)

        # get new_row as DataFrame
        new_row = data.to_pandas_series(remove_nan=False).to_frame().T
        new_row.set_index(["unix_timestamp"], inplace=True, drop=True)
        # check new_row index is not NaN or inf
        if new_row.index.isna() or new_row.index.isin([float("inf"), float("-inf")]):
            return devices
        new_row.index = new_row.index.astype("int64")  # convert index to int

        devices[data.serial_number] = pd.concat(
            [devices[data.serial_number], new_row], ignore_index=True
        )

        return devices

    def to_dict(self, remove_nan=True) -> dict[str, Union[int, float]]:
        if remove_nan:
            return {
                key: getattr(self, key)
                for key in self.__dataclass_fields__
                if getattr(self, key) is not None
            }
        else:
            return {key: getattr(self, key) for key in self.__dataclass_fields__}

    def to_pandas_series(self, remove_nan=True) -> pd.Series:
        """
        Convert the dataclass instance to a pandas Series.
        """
        data_dict = self.to_dict(remove_nan=remove_nan)
        return pd.Series(data_dict)

    # mandatory
    unix_timestamp: Optional[int] = None
    serial_number: Optional[int] = None
    connection_type: Optional[str] = None  # "serial", "connected", "advertisement"
    firmware_version: Optional[int] = None
    device_type: Optional[int] = 0  # 0: P2, 1: P1, 2: P2PRO, 3: P2PRO_CS
    device_status: Optional[int] = None  # bitmask

    # optional
    runtime_min: Optional[float] = None  # minutes since start
    ldsa: Optional[float] = None  # um**2/cm**3
    particle_number_concentration: Optional[float] = None  # particles/cm**3
    average_particle_diameter: Optional[float] = None  # nm
    particle_mass: Optional[float] = None  # ug/m**3
    particle_surface: Optional[float] = None  # um**2/m**3
    diffusion_current: Optional[float] = None  # nA
    diffusion_current_offset: Optional[float] = None  # nA
    diffusion_current_stddev: Optional[float] = None  # nA
    diffusion_current_delay_on: Optional[float] = None  # sec
    diffusion_current_delay_off: Optional[float] = None  # sec
    corona_voltage: Optional[float] = None  # V
    hires_adc1: Optional[float] = None  # momentanwert em 1
    hires_adc2: Optional[float] = None  # momentanwert em 2
    electrometer_1_amplitude: Optional[float] = None  # mV
    electrometer_2_amplitude: Optional[float] = None  # mV
    electrometer_1_gain: Optional[float] = None  # mV #TODO: check this unit
    electrometer_2_gain: Optional[float] = None  # mV #TODO: check this unit
    temperature: Optional[float] = None  # Celsius
    relative_humidity: Optional[float] = None  # percent 0-100
    deposition_voltage: Optional[float] = None  # V
    battery_voltage: Optional[float] = None  # V
    flow_from_dp: Optional[float] = None  # l/min
    ambient_pressure: Optional[float] = None  # hPa
    channel_pressure: Optional[float] = None  # hPa
    differential_pressure: Optional[float] = None  # Pa
    pump_voltage: Optional[float] = None  # V
    pump_current: Optional[float] = None  # mA
    pump_pwm: Optional[float] = None  # percent 0-100
    particle_number_10nm: Optional[float] = None  # /cm^3/log(d)
    particle_number_16nm: Optional[float] = None  # /cm^3/log(d)
    particle_number_26nm: Optional[float] = None  # /cm^3/log(d)
    particle_number_43nm: Optional[float] = None  # /cm^3/log(d)
    particle_number_70nm: Optional[float] = None  # /cm^3/log(d)
    particle_number_114nm: Optional[float] = None  # /cm^3/log(d)
    particle_number_185nm: Optional[float] = None  # /cm^3/log(d)
    particle_number_300nm: Optional[float] = None  # /cm^3/log(d)
    sigma_size_dist: Optional[float] = None  # gsd
    steps_inversion: Optional[float] = None  # steps count
    current_dist_0: Optional[float] = None  # mV
    current_dist_1: Optional[float] = None  # mV
    current_dist_2: Optional[float] = None  # mV
    current_dist_3: Optional[float] = None  # mV
    current_dist_4: Optional[float] = None  # mV

    supply_voltage_5V: Optional[float] = None  # V
    positive_voltage_3V3: Optional[float] = None  # V
    negative_voltage_3V3: Optional[float] = None  # V
    usb_cc_voltage: Optional[float] = None  # V

    cs_status: Optional[float] = None  # boolean, true or false


PARTECTOR1_DATA_STRUCTURE_V_LEGACY: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp": int,
    "runtime_min": float,
    "battery_voltage": float,
    "diffusion_current": float,
    "corona_voltage": float,
    "electrometer_1_amplitude": float,  # TODO: check with martin
    "DAC": float,  # TODO: check with martin
    "HVon": int,  # TODO: check with martin
    "idiffset": float,  # TODO: check with martin
    "flow_from_dp": float,
    "ldsa": float,
    "temperature": float,
    "relative_humidity": float,
    "device_status": int,
}


PARTECTOR2_DATA_STRUCTURE_V320: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp": int,
    "runtime_min": float,
    "diffusion_current": float,
    "corona_voltage": int,
    "hires_adc1": float,
    "hires_adc2": float,
    "electrometer_1_amplitude": float,
    "electrometer_2_amplitude": float,
    "temperature": float,
    "relative_humidity": int,
    "device_status": int,
    "deposition_voltage": int,
    "battery_voltage": float,
    "flow_from_dp": float,
    "ldsa": float,
    "average_particle_diameter": float,
    "particle_number_concentration": int,
    "differential_pressure": int,
    "ambient_pressure": float,
    "electrometer_1_gain": float,
    "electrometer_2_gain": float,
}

PARTECTOR2_DATA_STRUCTURE_V295_V297_V298: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp": int,
    "runtime_min": float,
    "diffusion_current": float,
    "corona_voltage": int,
    "hires_adc1": float,
    "hires_adc2": float,
    "electrometer_1_amplitude": float,
    "electrometer_2_amplitude": float,
    "temperature": float,
    "relative_humidity": int,
    "device_status": int,
    "deposition_voltage": int,
    "battery_voltage": float,
    "flow_from_dp": float,
    "ldsa": float,
    "average_particle_diameter": float,
    "particle_number_concentration": int,
    "differential_pressure": int,
    "ambient_pressure": float,
}

PARTECTOR2_DATA_STRUCTURE_V265_V275: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp": int,
    "runtime_min": float,
    "diffusion_current": float,
    "corona_voltage": int,
    "hires_adc1": float,
    "hires_adc2": float,
    "electrometer_1_amplitude": float,
    "electrometer_2_amplitude": float,
    "temperature": float,
    "relative_humidity": int,
    "device_status": int,
    "deposition_voltage": int,
    "battery_voltage": float,
    "flow_from_dp": float,
    "ldsa": float,
    "average_particle_diameter": float,
    "particle_number_concentration": int,
    "differential_pressure": int,
    "ambient_pressure": float,
    "lag": int,  # not used anymore
}

PARTECTOR2_DATA_STRUCTURE_LEGACY: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp": int,
    "runtime_min": float,
    "diffusion_current": float,
    "corona_voltage": int,
    "hires_adc1": float,
    "hires_adc2": float,
    "electrometer_1_amplitude": float,
    "electrometer_2_amplitude": float,
    "temperature": float,
    "relative_humidity": int,
    "device_status": int,
    "deposition_voltage": int,
    "battery_voltage": float,
    "flow_from_dp": float,
    "ldsa": float,
    "average_particle_diameter": float,
    "particle_number_concentration": int,
    "differential_pressure": int,
    "ambient_pressure": float,
}


PARTECTOR2_PRO_DATA_STRUCTURE_V311: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp": int,
    "runtime_min": float,
    "particle_number_concentration": int,
    "average_particle_diameter": float,
    "ldsa": float,
    "surface": float,  # not existing in protobuf
    "particle_mass": float,
    "sigma_size_dist": float,  # not existing in protobuf
    "diffusion_current": float,
    "corona_voltage": int,
    "deposition_voltage": int,
    "temperature": float,
    "relative_humidity": int,
    "ambient_pressure": float,
    "flow_from_dp": float,
    "battery_voltage": float,
    "pump_current": float,  # not existing in protobuf
    "device_status": int,
    "pump_pwm": int,  # not existing in protobuf
    "steps": int,  # not existing in protobuf
    "particle_number_10nm": int,
    "particle_number_16nm": int,
    "particle_number_26nm": int,
    "particle_number_43nm": int,
    "particle_number_70nm": int,
    "particle_number_114nm": int,
    "particle_number_185nm": int,
    "particle_number_300nm": int,
    "current_dist_0": float,  # not existing in protobuf
    "current_dist_1": float,  # not existing in protobuf
    "current_dist_2": float,  # not existing in protobuf
    "current_dist_3": float,  # not existing in protobuf
    "current_dist_4": float,  # not existing in protobuf
    "electrometer_1_gain": float,
    "electrometer_2_gain": float,
}

PARTECTOR2_PRO_DATA_STRUCTURE_V336: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp": int,
    "runtime_min": float,
    "particle_number_concentration": int,
    "average_particle_diameter": float,
    "ldsa": float,
    "surface": float,  # not existing in protobuf
    "particle_mass": float,
    "sigma_size_dist": float,  # not existing in protobuf
    "diffusion_current": float,
    "corona_voltage": int,
    "deposition_voltage": int,
    "temperature": float,
    "relative_humidity": int,
    "ambient_pressure": float,
    "flow_from_dp": float,
    "battery_voltage": float,
    "pump_current": float,  # not existing in protobuf
    "device_status": int,
    "flow_from_phase_angle": float,  # not existing in protobuf
    "steps": int,  # not existing in protobuf
    "particle_number_10nm": int,
    "particle_number_16nm": int,
    "particle_number_26nm": int,
    "particle_number_43nm": int,
    "particle_number_70nm": int,
    "particle_number_114nm": int,
    "particle_number_185nm": int,
    "particle_number_300nm": int,
    "current_dist_0": float,
    "current_dist_1": float,
    "current_dist_2": float,
    "current_dist_3": float,
    "current_dist_4": float,
    "electrometer_1_gain": float,
    "electrometer_2_gain": float,
}

PARTECTOR2_PRO_CS_DATA_STRUCTURE_V315: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp": int,
    "runtime_min": float,
    "particle_number_concentration": int,
    "average_particle_diameter": float,
    "ldsa": float,
    "surface": float,  # not existing in protobuf
    "particle_mass": float,
    "sigma_size_dist": float,  # not existing in protobuf
    "diffusion_current": float,
    "corona_voltage": int,
    "deposition_voltage": int,
    "temperature": float,
    "relative_humidity": int,
    "ambient_pressure": float,
    "flow_from_dp": float,
    "battery_voltage": float,
    "pump_current": float,  # not existing in protobuf
    "device_status": int,
    "pump_pwm": int,  # not existing in protobuf
    "steps": int,  # not existing in protobuf
    "particle_number_10nm": int,
    "particle_number_16nm": int,
    "particle_number_26nm": int,
    "particle_number_43nm": int,
    "particle_number_70nm": int,
    "particle_number_114nm": int,
    "particle_number_185nm": int,
    "particle_number_300nm": int,
    "current_dist_0": float,
    "current_dist_1": float,
    "current_dist_2": float,
    "current_dist_3": float,
    "current_dist_4": float,
    "electrometer_1_gain": float,
    "electrometer_2_gain": float,
    "cs_status": int,
}

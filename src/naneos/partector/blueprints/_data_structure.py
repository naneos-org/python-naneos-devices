from dataclasses import dataclass
from typing import Optional, Union

import pandas as pd

# NaneosDeviceDataDict should have format {serial_number: pd.DataFrame}
# the pd.DataFrame is multiindex with unix_timestamp and connection_type as index


def sort_and_clean_naneos_data(data: dict[int, pd.DataFrame]) -> dict[int, pd.DataFrame]:
    """
    Sorts the DataFrame by unix_timestamp and connection_type, and removes columns with all NaN values.
    """
    data_return = {}

    for serial, df in data.items():
        df = df.dropna(axis=1, how="all")  # drop columns with all NaN values

        if "connection_type" in df.columns:
            df.reset_index(inplace=True)
            df.set_index(["unix_timestamp", "connection_type"], inplace=True)
            df = df.sort_index(level=[0, 1], ascending=[True, True])
            # drop connection_type index and make it a column
            df.reset_index(level=1, drop=False, inplace=True)
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
    def add_serial_data_to_dict(
        devices: dict, data: "NaneosDeviceDataPoint"
    ) -> dict[int, pd.DataFrame]:
        if data.serial_number not in devices:
            devices[data.serial_number] = pd.DataFrame()

        # remove oldes row if there are more than 300 rows
        if len(devices[data.serial_number]) > 300:
            devices[data.serial_number].drop(devices[data.serial_number].index[0], inplace=True)
        # add new row
        new_row = data.to_pandas_series(remove_nan=False).to_frame().T
        new_row["connection_type"] = "serial"
        new_row.set_index(["unix_timestamp"], inplace=True, drop=True)
        new_row.index = new_row.index.astype("int")  # convert index to int
        devices[data.serial_number] = pd.concat(
            [devices[data.serial_number], new_row], ignore_index=False
        )

        return devices

    @staticmethod
    def add_connected_data_to_dict(
        devices: dict, data: "NaneosDeviceDataPoint"
    ) -> dict[int, pd.DataFrame]:
        if data.serial_number not in devices:
            devices[data.serial_number] = pd.DataFrame()

        # remove oldes row if there are more than 300 rows
        if len(devices[data.serial_number]) > 300:
            devices[data.serial_number].drop(devices[data.serial_number].index[0], inplace=True)
        # add new row with an coulmn connection_type = "connected"
        new_row = data.to_pandas_series(remove_nan=False).to_frame().T
        new_row["connection_type"] = "connected"
        new_row.set_index(["unix_timestamp"], inplace=True, drop=True)
        new_row.index = new_row.index.astype("int")  # convert index to int
        devices[data.serial_number] = pd.concat(
            [devices[data.serial_number], new_row], ignore_index=False
        )

        return devices

    @staticmethod
    def add_advertisement_data_to_dict(
        devices: dict, data: "NaneosDeviceDataPoint"
    ) -> dict[int, pd.DataFrame]:
        if data.serial_number not in devices:
            devices[data.serial_number] = pd.DataFrame()

        # remove oldes row if there are more than 300 rows
        if len(devices[data.serial_number]) > 300:
            devices[data.serial_number].drop(devices[data.serial_number].index[0], inplace=True)
        # add new row
        new_row = data.to_pandas_series(remove_nan=False).to_frame().T
        new_row["connection_type"] = "advertisement"
        new_row.set_index(["unix_timestamp"], inplace=True, drop=True)
        new_row.index = new_row.index.astype("int")  # convert index to int
        devices[data.serial_number] = pd.concat(
            [devices[data.serial_number], new_row], ignore_index=False
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
    firmware_version: Optional[str] = None
    device_type: Optional[int] = 0  # 0: P2, 1: P1, 2: P2PRO, 3: P2PRO_CS

    # optional
    runtime_min: Optional[float] = None
    device_status: Optional[int] = None
    ldsa: Optional[float] = None
    particle_number_concentration: Optional[float] = None
    average_particle_diameter: Optional[float] = None
    particle_mass: Optional[float] = None
    particle_surface: Optional[float] = None
    diffusion_current: Optional[float] = None
    diffusion_current_offset: Optional[float] = None
    diffusion_current_stddev: Optional[float] = None
    diffusion_current_delay_on: Optional[float] = None
    diffusion_current_delay_off: Optional[float] = None
    corona_voltage: Optional[float] = None
    hires_adc1: Optional[float] = None  # momentanwert em 1
    hires_adc2: Optional[float] = None  # momentanwert em 2
    electrometer_1_amplitude: Optional[float] = None
    electrometer_2_amplitude: Optional[float] = None
    electrometer_1_gain: Optional[float] = None
    electrometer_2_gain: Optional[float] = None
    temperature: Optional[float] = None
    relative_humidity: Optional[float] = None
    deposition_voltage: Optional[float] = None
    battery_voltage: Optional[float] = None
    flow_from_dp: Optional[float] = None
    ambient_pressure: Optional[float] = None
    channel_pressure: Optional[float] = None
    differential_pressure: Optional[float] = None
    pump_voltage: Optional[float] = None
    pump_current: Optional[float] = None
    pump_pwm: Optional[float] = None
    particle_number_10nm: Optional[float] = None
    particle_number_16nm: Optional[float] = None
    particle_number_26nm: Optional[float] = None
    particle_number_43nm: Optional[float] = None
    particle_number_70nm: Optional[float] = None
    particle_number_114nm: Optional[float] = None
    particle_number_185nm: Optional[float] = None
    particle_number_300nm: Optional[float] = None
    sigma_size_dist: Optional[float] = None
    steps_inversion: Optional[float] = None
    current_dist_0: Optional[float] = None
    current_dist_1: Optional[float] = None
    current_dist_2: Optional[float] = None
    current_dist_3: Optional[float] = None
    current_dist_4: Optional[float] = None

    supply_voltage_5V: Optional[float] = None
    positive_voltage_3V3: Optional[float] = None
    negative_voltage_3V3: Optional[float] = None
    usb_cc_voltage: Optional[float] = None

    cs_status: Optional[float] = None


# TODO: from here on its old code, need to be updated
PARTECTOR1_DATA_STRUCTURE_V_LEGACY: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp_ms": int,
    "runtime_min": float,
    "batt_voltage": float,
    "idiff_global": float,
    "ucor_global": float,
    "EM": float,
    "DAC": float,
    "HVon": int,
    "idiffset": float,
    "flow_from_dp": float,
    "LDSA": float,
    "T": float,
    "RHcorr": float,
    "device_status": int,
    # "phase_angle": float,
}

# data structure for Partector2 320 and higher
# lower give error and recommend update

PARTECTOR2_DATA_STRUCTURE_V320: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp_ms": int,
    "runtime_min": float,
    "idiff_global": float,
    "ucor_global": int,
    "hiresADC1": float,
    "hiresADC2": float,
    "EM_amplitude1": float,
    "EM_amplitude2": float,
    "T": float,
    "RHcorr": int,
    "device_status": int,
    "deposition_voltage": int,
    "batt_voltage": float,
    "flow_from_dp": float,
    "LDSA": float,
    "diameter": float,
    "number": int,
    "dP": int,
    "P_average": float,
    "em_gain1": float,
    "em_gain2": float,
}

PARTECTOR2_DATA_STRUCTURE_V295_V297_V298: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp_ms": int,
    "runtime_min": float,
    "idiff_global": float,
    "ucor_global": int,
    "hiresADC1": float,
    "hiresADC2": float,
    "EM_amplitude1": float,
    "EM_amplitude2": float,
    "T": float,
    "RHcorr": int,
    "device_status": int,
    "deposition_voltage": int,
    "batt_voltage": float,
    "flow_from_dp": float,
    "LDSA": float,
    "diameter": float,
    "number": int,
    "dP": int,
    "P_average": float,
}

PARTECTOR2_DATA_STRUCTURE_V265_V275: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp_ms": int,
    "runtime_min": float,
    "idiff_global": float,
    "ucor_global": int,
    "hiresADC1": float,
    "hiresADC2": float,
    "EM_amplitude1": float,
    "EM_amplitude2": float,
    "T": float,
    "RHcorr": int,
    "device_status": int,
    "deposition_voltage": int,
    "batt_voltage": float,
    "flow_from_dp": float,
    "LDSA": float,
    "diameter": float,
    "number": int,
    "dP": int,
    "P_average": float,
    "lag": int,
}

PARTECTOR2_DATA_STRUCTURE_LEGACY: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp_ms": int,
    "runtime_min": float,
    "idiff_global": float,
    "ucor_global": int,
    "hiresADC1": float,
    "hiresADC2": float,
    "EM_amplitude1": float,
    "EM_amplitude2": float,
    "T": float,
    "RHcorr": int,
    "device_status": int,
    "deposition_voltage": int,
    "batt_voltage": float,
    "flow_from_dp": float,
    "LDSA": float,
    "diameter": float,
    "number": int,
    "dP": int,
    "P_average": float,
}


PARTECTOR2_PRO_DATA_STRUCTURE_V311: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp_ms": int,
    "runtime_min": float,
    "number": int,
    "diameter": float,
    "LDSA": float,
    "surface": float,  # not existing in protobuf
    "particle_mass": float,
    "sigma_size_dist": float,  # not existing in protobuf
    "idiff_global": float,
    "ucor_global": int,
    "deposition_voltage": int,
    "T": float,
    "RHcorr": int,
    "P_average": float,
    "flow_from_dp": float,
    "batt_voltage": float,
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
    "current_0": float,  # not existing in protobuf
    "current_1": float,  # not existing in protobuf
    "current_2": float,  # not existing in protobuf
    "current_3": float,  # not existing in protobuf
    "current_4": float,  # not existing in protobuf
    "em_gain1": float,
    "em_gain2": float,
}

PARTECTOR2_PRO_DATA_STRUCTURE_V336: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp_ms": int,
    "runtime_min": float,
    "number": int,
    "diameter": float,
    "LDSA": float,
    "surface": float,  # not existing in protobuf
    "particle_mass": float,
    "sigma_size_dist": float,  # not existing in protobuf
    "idiff_global": float,
    "ucor_global": int,
    "deposition_voltage": int,
    "T": float,
    "RHcorr": int,
    "P_average": float,
    "flow_from_dp": float,
    "batt_voltage": float,
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
    "current_0": float,
    "current_1": float,
    "current_2": float,
    "current_3": float,
    "current_4": float,
    "em_gain1": float,
    "em_gain2": float,
}

PARTECTOR2_PRO_CS_DATA_STRUCTURE_V315: dict[str, Union[type[int], type[float]]] = {
    "unix_timestamp_ms": int,
    "runtime_min": float,
    "number": int,
    "diameter": float,
    "LDSA": float,
    "surface": float,  # not existing in protobuf
    "particle_mass": float,
    "sigma_size_dist": float,  # not existing in protobuf
    "idiff_global": float,
    "ucor_global": int,
    "deposition_voltage": int,
    "T": float,
    "RHcorr": int,
    "P_average": float,
    "flow_from_dp": float,
    "batt_voltage": float,
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
    "current_0": float,
    "current_1": float,
    "current_2": float,
    "current_3": float,
    "current_4": float,
    "em_gain1": float,
    "em_gain2": float,
    "cs_status": int,
}

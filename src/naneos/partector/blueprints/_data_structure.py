from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class Partector2DataStructure:
    def to_dict(self, remove_nan=True) -> dict[str, Union[int, float]]:
        if remove_nan:
            return {
                key: getattr(self, key)
                for key in self.__dataclass_fields__
                if getattr(self, key) is not None
            }
        else:
            return {key: getattr(self, key) for key in self.__dataclass_fields__}

    # mandatory
    unix_timestamp: Optional[int] = None

    # optional
    runtime_min: Optional[float] = None
    device_status: Optional[int] = None
    ldsa: Optional[float] = None
    particle_number: Optional[int] = None
    particle_diameter: Optional[float] = None
    particle_mass: Optional[float] = None
    particle_surface: Optional[float] = None
    diffusion_current: Optional[float] = None
    diffusion_current_offset: Optional[float] = None
    corona_voltage: Optional[int] = None
    hires_adc1: Optional[float] = None
    hires_adc2: Optional[float] = None
    em_amplitude1: Optional[float] = None
    em_amplitude2: Optional[float] = None
    em_gain1: Optional[int] = None
    em_gain2: Optional[int] = None
    temperature: Optional[float] = None
    relativ_humidity: Optional[int] = None
    deposition_voltage: Optional[int] = None
    battery_voltage: Optional[float] = None
    flow_from_dp: Optional[float] = None
    differential_pressure: Optional[int] = None
    ambient_pressure: Optional[float] = None
    sigma: Optional[float] = None
    pump_current: Optional[float] = None
    pump_pwm: Optional[int] = None
    dist_steps: Optional[int] = None
    dist_particle_number_10nm: Optional[int] = None
    dist_particle_number_16nm: Optional[int] = None
    dist_particle_number_26nm: Optional[int] = None
    dist_particle_number_43nm: Optional[int] = None
    dist_particle_number_70nm: Optional[int] = None
    dist_particle_number_114nm: Optional[int] = None
    dist_particle_number_185nm: Optional[int] = None
    dist_particle_number_300nm: Optional[int] = None
    dist_current_0: Optional[float] = None
    dist_current_1: Optional[float] = None
    dist_current_2: Optional[float] = None
    dist_current_3: Optional[float] = None
    dist_current_4: Optional[float] = None
    cs_status: Optional[int] = None


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
    "sigma": float,  # not existing in protobuf
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
    "sigma": float,  # not existing in protobuf
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
    "sigma": float,  # not existing in protobuf
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

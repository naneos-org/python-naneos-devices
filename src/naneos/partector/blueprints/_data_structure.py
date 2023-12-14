from dataclasses import dataclass
import datetime
from typing import Optional


@dataclass
class Partector2DataStructure:
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


# v295
PARTECTOR2_DATA_STRUCTURE = {
    "dateTime": datetime.datetime,
    "runtime_min": Optional[float],
    "idiff_global": Optional[float],
    "ucor_global": Optional[int],
    "hiresADC1": Optional[float],
    "hiresADC2": Optional[float],
    "EM_amplitude1": Optional[float],
    "EM_amplitude2": Optional[float],
    "T": Optional[float],
    "RHcorr": Optional[int],
    "device_status": Optional[int],
    "deposition_voltage": Optional[int],
    "batt_voltage": Optional[float],
    "flow_from_dp": Optional[float],
    "LDSA": Optional[float],
    "diameter": Optional[float],
    "number": Optional[int],
    "dP": Optional[int],
    "P_average": Optional[float],
}

# v302
PARTECTOR2_PRO_DATA_STRUCTURE = {
    "dateTime": datetime.datetime,
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
}

# same as PARTECTOR2_PRO_DATA_STRUCTURE but with cs_status at the end
PARTECTOR2_PRO_GARAGE_DATA_STRUCTURE = PARTECTOR2_PRO_DATA_STRUCTURE.copy()
PARTECTOR2_PRO_GARAGE_DATA_STRUCTURE["cs_status"] = int


PARTECTOR1_DATA_STRUCTURE = {
    "dateTime": datetime.datetime,
    "runtime_min": float,
    "batt_voltage": float,
    "idiff_global": float,
    "ucor_global": float,
    "EM": float,
    "DAC": float,
    "HVon": int,
    "idiffset": float,
    "flow": float,
    "LDSA": float,
    "T": float,
    "RHcorr": float,
    "device_status": int,
    # "phase_angle": float,
}

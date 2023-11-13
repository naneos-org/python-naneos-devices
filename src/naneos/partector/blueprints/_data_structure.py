import datetime

# v295
PARTECTOR2_DATA_STRUCTURE = {
    "dateTime": datetime.datetime,
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

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


def get_p2_idx(key: str) -> int:
    return list(PARTECTOR2_DATA_STRUCTURE.keys()).index(key)


def get_p1_idx(key: str) -> int:
    return list(PARTECTOR1_DATA_STRUCTURE.keys()).index(key)

import datetime

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
    "lag": float,
}


def get_p2_idx(key: str) -> int:
    return list(PARTECTOR2_DATA_STRUCTURE.keys()).index(key)

# TODO: this is deprecated remove in future

from math import pi

from naneos.partector.blueprints._data_structure import get_p2_idx as get_i


def _get_lambda_upload_list_serial(data_list: list, serial_number: int) -> list:
    upload_list = []

    for entry in data_list:
        mass = __calc_particle_mass(entry[get_i("number")], entry[get_i("diameter")])
        upload_dict = {
            "deviceName": "P2",
            "timestamp": int(entry[get_i("dateTime")].timestamp()),
            "locationData": {"latitude": 0.0, "longitude": 0.0},  # TODO: implement
            "partectorData": {
                "average_particle_diameter": entry[get_i("diameter")],
                "battery_voltage": entry[get_i("batt_voltage")],
                "device_status": entry[get_i("device_status")],
                "ldsa": entry[get_i("LDSA")],
                "particle_mass": mass,
                "particle_number_concentration": entry[get_i("number")],
                "relative_humidity": entry[get_i("RHcorr")],
                "serial_number": serial_number,
                "temperature": entry[get_i("T")],
            },
        }
        upload_list.append(upload_dict)

    return upload_list


def __calc_particle_mass(number, diameter):
    """Calculates the particle_mass from number and diameter.
    Due to Martin the obtained values are very uncertain."""
    return number * pi * 6.38 / 6.0 * pow(diameter, 3) * 1.2e-9

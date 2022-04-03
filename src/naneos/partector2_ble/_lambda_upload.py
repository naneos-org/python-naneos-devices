def _get_lambda_upload_list_ble(data_dict: dict, sn_exclude: list = []) -> list:
    """
    Returns a list of dicts with the data to upload to lambda.
    :param data_dict:
    :param sn_exclude:
    :return:
    """
    data_list = []
    for sn, data in data_dict.items():
        if sn in sn_exclude:
            continue

        for entry in data:
            upload_dict = {
                "deviceName": "P2",
                "timestamp": int(entry["dateTime"].timestamp()),
                # TODO: implement
                "locationData": {"latitude": 0.0, "longitude": 0.0},
                "partectorData": {
                    "average_particle_diameter": entry["diameter"],
                    "battery_voltage": entry["batt_voltage"],
                    "device_status": entry["device_status"],
                    "ldsa": entry["LDSA"],
                    "particle_mass": entry["particle_mass"],
                    "particle_number_concentration": entry["number"],
                    "relative_humidity": entry["RHcorr"],
                    "serial_number": sn,
                    "temperature": entry["T"],
                },
            }
            data_list.append(upload_dict)

    return data_list
    # data_dict structure: structure =
    # {8000: [["data_list"], ["data_list"]], 8001: [["data_list"], ["data_list"]]}
    # serial numbers exclude: when fetching from serial and ble, prefer serial data

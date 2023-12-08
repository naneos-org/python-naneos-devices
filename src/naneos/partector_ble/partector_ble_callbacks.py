from bleak.backends.characteristic import BleakGATTCharacteristic


class PartectorBleCallbacks:
    def __init__(self, serial_number: int) -> None:
        self.serial_number: int = serial_number

    def callback_std(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        print(f"Received data from {self.serial_number}: {data}")

        measurement = {
            "ldsa": int.from_bytes(data[0:3], byteorder="little") / 100.0,
            "diameter": int.from_bytes(data[3:5], byteorder="little"),
            "number": int.from_bytes(data[5:8], byteorder="little"),
            "T": int.from_bytes(data[8:9], byteorder="little"),
            "RHcorr": int.from_bytes(data[9:10], byteorder="little"),
            "device_status": int.from_bytes(data[10:12], byteorder="little")
            + (((int(data[19]) >> 1) & 0b01111111) << 16),
            "batt_voltage": int.from_bytes(data[12:14], byteorder="little") / 100.0,
            "particle_mass": int.from_bytes(data[14:18], byteorder="little") / 100.0,
        }

        print(measurement)

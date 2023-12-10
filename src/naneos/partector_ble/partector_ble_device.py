from typing import Optional
from venv import logger

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.scanner import AdvertisementData

from naneos.logger import LEVEL_INFO, get_naneos_logger

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleDevice:
    def __init__(self, serial_number: int) -> None:
        self.serial_number: int = serial_number

    def callback_std(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
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

        logger.debug(f"Callback std from {self.serial_number} with data: {measurement}")

    # Methods for the advertisement
    @classmethod
    def get_naneos_adv(cls, data: AdvertisementData) -> tuple[Optional[bytes], Optional[int]]:
        """
        Returns the custom advertisement data from Naneos devices.

        We are violating the BLE standard here by using the manufacturer data field for our own purposes.
        """
        # Because of the 22 byte limit we also encoded data into the manufacturer name field.
        naneos_adv = next(iter(data.manufacturer_data.keys())).to_bytes(2, byteorder="little")

        # security check 1: First byte must be "X"
        if naneos_adv[0].to_bytes(1).decode("utf-8") != "X":
            return (None, None)

        # add the data part of the manufacturer data
        naneos_adv += next(iter(data.manufacturer_data.values()))

        # security check 2: The data must be 22 bytes long
        if len(naneos_adv) != 22:
            return (None, None)

        serial_number = cls.get_serial_number(naneos_adv)

        return (naneos_adv, serial_number)

    @staticmethod
    def get_serial_number(data: bytes) -> int:
        return int.from_bytes(data[15:17], byteorder="little")

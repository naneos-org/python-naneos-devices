from collections import deque
import time
from typing import Optional

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.scanner import AdvertisementData

from naneos.logger import LEVEL_DEBUG, LEVEL_INFO, get_naneos_logger
from naneos.partector.blueprints._data_structure import Partector2DataStructure

logger = get_naneos_logger(__name__, LEVEL_DEBUG)


class PartectorBleDevice:
    def __init__(self, serial_number: int) -> None:
        self.serial_number: int = serial_number
        self.ble_client: Optional[BleakClient] = None
        self._data_queue: deque[Partector2DataStructure] = deque(maxlen=100)

    def _add_old_format_data(self, data: AdvertisementData, serial_number: int) -> None:
        """Adds data from old format to the data queue"""
        adv, sn_compare = self.get_naneos_adv(data)

        if sn_compare != serial_number or adv is None:
            logger.warning(
                f"Serial number from advertisement data ({sn_compare}) does not match serial number from connection ({serial_number})"
            )
            return None

        decoded_data = self.decode_std_chareristic(bytearray(adv))
        decoded_data.unix_timestamp = int(time.time())

        if len(self._data_queue) == self._data_queue.maxlen:
            self._data_queue.popleft()
        self._data_queue.append(decoded_data)

        logger.debug(f"Added old format data from {self.serial_number}")

    def callback_std(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        timestamp = int(time.time())
        decoded_data = self.decode_std_chareristic(data)
        decoded_data.unix_timestamp = timestamp
        if len(self._data_queue) == self._data_queue.maxlen:
            self._data_queue.popleft()
        self._data_queue.append(decoded_data)

        logger.debug(f"Callback std from {self.serial_number}")

    def callback_aux(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        decoded_data = self.decode_aux_characteristic(data)
        if self._data_queue:
            for field in self._data_queue[-1].__dataclass_fields__:
                if getattr(decoded_data, field) is not None:
                    setattr(self._data_queue[-1], field, getattr(decoded_data, field))

        logger.debug(f"Callback aux from {self.serial_number}")

    def callback_size_dist(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        decoded_data = self.decode_size_dist_characteristic(data)
        if self._data_queue:
            for field in self._data_queue[-1].__dataclass_fields__:
                if getattr(decoded_data, field) is not None:
                    setattr(self._data_queue[-1], field, getattr(decoded_data, field))

        logger.debug(f"Callback size_dist from {self.serial_number}")

    def callback_read(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        decoded_data = data.decode("utf-8").replace("\r", "").replace("\n", "")
        logger.info(f"Callback read from {self.serial_number}: {decoded_data}")

    @staticmethod
    def decode_std_chareristic(data: bytearray) -> Partector2DataStructure:
        decoded_data = Partector2DataStructure(
            ldsa=int.from_bytes(data[0:3], byteorder="little") / 100.0,
            particle_diameter=int.from_bytes(data[3:5], byteorder="little"),
            particle_number=int.from_bytes(data[5:8], byteorder="little"),
            temperature=int.from_bytes(data[8:9], byteorder="little"),
            relativ_humidity=int.from_bytes(data[9:10], byteorder="little"),
            device_status=int.from_bytes(data[10:12], byteorder="little")
            + (((int(data[19]) >> 1) & 0b01111111) << 16),
            battery_voltage=int.from_bytes(data[12:14], byteorder="little") / 100.0,
            particle_mass=int.from_bytes(data[14:18], byteorder="little") / 100.0,
        )

        return decoded_data

    @staticmethod
    def decode_aux_characteristic(data: bytearray) -> Partector2DataStructure:
        decoded_data = Partector2DataStructure(
            corona_voltage=int.from_bytes(data[0:2], byteorder="little"),
            diffusion_current=int.from_bytes(data[2:4], byteorder="little") / 100.0,
            deposition_voltage=int.from_bytes(data[4:6], byteorder="little"),
            flow_from_dp=int.from_bytes(data[6:8], byteorder="little"),
            ambient_pressure=int.from_bytes(data[8:10], byteorder="little"),
            em_amplitude1=int.from_bytes(data[10:12], byteorder="little"),
            em_amplitude2=int.from_bytes(data[12:14], byteorder="little"),
            em_gain1=int.from_bytes(data[14:16], byteorder="little"),
            em_gain2=int.from_bytes(data[16:18], byteorder="little"),
            diffusion_current_offset=int.from_bytes(data[18:20], byteorder="little"),
        )

        return decoded_data

    @staticmethod
    def decode_size_dist_characteristic(data: bytearray) -> Partector2DataStructure:
        decoded_data = Partector2DataStructure(
            dist_particle_number_10nm=int.from_bytes(data[0:3], byteorder="little"),
            dist_particle_number_16nm=int.from_bytes(data[3:6], byteorder="little"),
            dist_particle_number_26nm=int.from_bytes(data[6:9], byteorder="little"),
            dist_particle_number_43nm=int.from_bytes(data[9:12], byteorder="little"),
            dist_particle_number_70nm=int.from_bytes(data[12:15], byteorder="little"),
            dist_particle_number_114nm=int.from_bytes(data[15:18], byteorder="little"),
            dist_particle_number_185nm=int.from_bytes(data[18:21], byteorder="little"),
            dist_particle_number_300nm=int.from_bytes(data[21:24], byteorder="little"),
        )

        return decoded_data

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

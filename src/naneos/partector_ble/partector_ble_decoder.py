from typing import Optional

from bleak.backends.scanner import AdvertisementData

from naneos.logger import LEVEL_INFO, get_naneos_logger

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleDecoder:
    """
    Decode the BLE data from the Partector device.
    """

    def __init__(self):
        pass

    # @classmethod
    # def get_naneos_adv(cls, adv: AdvertisementData) -> tuple[Optional[bytes], Optional[int]]:

    #     serial_number = cls.get_serial_number(naneos_adv)

    #     return (naneos_adv, serial_number)

    @staticmethod
    def _get_adv_bytes(adv: AdvertisementData) -> bytes:
        """
        Returns the full advertisement data from the Partector device.
        We are violating the BLE standard here by using the manufacturer data field for our own purposes.
        """
        man = adv.manufacturer_data
        adv_1 = next(iter(man.keys())).to_bytes(2, "big")
        adv_2 = next(iter(man.values()))
        adv_bytes = adv_1 + adv_2

        return adv_bytes

    @staticmethod
    def _check_data_format(data: bytes) -> bool:
        """
        Check if the data format is valid.
        """
        if len(data) not in {22, 44} or data[1] != 0x58:
            return False

        return True

    @staticmethod
    def get_serial_number(data: bytes) -> int:
        return int.from_bytes(data[15:17], byteorder="little")

    @classmethod
    def decode_std_chareristic(cls, adv: AdvertisementData) -> Optional[bytes]:
        """
        Decode the standard characteristic data from the Partector device.
        """

        adv_bytes = PartectorBleDecoder._get_adv_bytes(adv)
        if not cls._check_data_format(adv_bytes):
            return None

        logger.debug(f"Serial Number: {cls.get_serial_number(adv_bytes)}")  # just for debug reasons

        return adv_bytes

from typing import Optional

from bleak.backends.scanner import AdvertisementData

from naneos.logger import LEVEL_INFO, get_naneos_logger

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleDecoder:
    """
    Decode the BLE data from the Partector device.
    """

    VALID_DATA_LENGTHS = {22, 44}
    EXPECTED_HEADER_BYTE = 0x58

    # == Public Methods ============================================================================
    @classmethod
    def decode_partector_advertisement(cls, adv: AdvertisementData) -> Optional[bytes]:
        """
        Decode the standard characteristic data from the Partector device.
        """

        adv_bytes = PartectorBleDecoder._get_adv_bytes(adv)
        if not cls._check_data_format(adv_bytes):
            return None

        return adv_bytes

    @staticmethod
    def _get_adv_bytes(adv: AdvertisementData) -> bytes:
        """
        Returns the full advertisement data from the Partector device.
        We are violating the BLE standard here by using the manufacturer data field for our own purposes.
        This is not a good practice, but it was the only way to put more data into the advertisement.
        """
        manufacturer_data = adv.manufacturer_data
        manufacturer_id_bytes = next(iter(manufacturer_data.keys())).to_bytes(2, "big")
        manufacturer_payload = next(iter(manufacturer_data.values()))
        adv_bytes = manufacturer_id_bytes + manufacturer_payload

        return adv_bytes

    @classmethod
    def _check_data_format(cls, data: bytes) -> bool:
        """
        Check if the data format is valid.
        """
        if len(data) not in cls.VALID_DATA_LENGTHS or data[1] != cls.EXPECTED_HEADER_BYTE:
            return False

        return True

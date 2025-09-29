from typing import Optional

from bleak.backends.scanner import AdvertisementData

from naneos.logger import LEVEL_WARNING, get_naneos_logger

logger = get_naneos_logger(__name__, LEVEL_WARNING)


class PartectorBleDecoder:
    """
    Decode the BLE data from the Partector device.
    """

    VALID_DATA_LENGTHS = {22, 44}

    EXPECTED_PROTOCOL_BYTE_1 = "X".encode("utf-8")[0]
    EXPECTED_PROTOCOL_BYTE_1_POSITION = 0
    EXPECTED_PROTOCOL_BYTE_2 = "F".encode("utf-8")[0]
    EXPECTED_PROTOCOL_BYTE_2_POSITION = 21

    EXPECTED_PROTOCOL_BYTE_3 = "Y".encode("utf-8")[0]
    EXPECTED_PROTOCOL_BYTE_3_POSITION = 22
    EXPECTED_PROTOCOL_BYTE_4 = "F".encode("utf-8")[0]
    EXPECTED_PROTOCOL_BYTE_4_POSITION = 43

    SLICE_ADVERTISEMENT = slice(1, 21)
    SLICE_SCAN_RESPONSE = slice(23, 43)

    # == Public Methods ============================================================================
    @classmethod
    def decode_partector_advertisement(
        cls, adv: AdvertisementData
    ) -> Optional[tuple[bytes, Optional[bytes]]]:
        """
        Decode the standard characteristic data from the Partector device.
        """

        adv_bytes = PartectorBleDecoder._get_adv_bytes(adv)
        if not cls._check_data_format(adv_bytes):
            return None

        return cls._remove_protocol_bytes(adv_bytes)

    @staticmethod
    def _get_adv_bytes(adv: AdvertisementData) -> bytes:
        """
        Returns the full advertisement data from the Partector device.
        We are violating the BLE standard here by using the manufacturer data field for our own purposes.
        This is not a good practice, but it was the only way to put more data into the advertisement.
        """
        manufacturer_data = adv.manufacturer_data
        manufacturer_id_bytes = next(iter(manufacturer_data.keys())).to_bytes(2, "little")
        manufacturer_payload = next(iter(manufacturer_data.values()))
        adv_bytes = manufacturer_id_bytes + manufacturer_payload

        return adv_bytes

    @classmethod
    def _check_data_format(cls, data: bytes) -> bool:
        """
        Check if the data format is valid.
        """

        if len(data) not in cls.VALID_DATA_LENGTHS:
            return False

        if (
            data[cls.EXPECTED_PROTOCOL_BYTE_1_POSITION] != cls.EXPECTED_PROTOCOL_BYTE_1
            or data[cls.EXPECTED_PROTOCOL_BYTE_2_POSITION] != cls.EXPECTED_PROTOCOL_BYTE_2
        ):
            return False

        if len(data) > 22:
            if (
                data[cls.EXPECTED_PROTOCOL_BYTE_3_POSITION] != cls.EXPECTED_PROTOCOL_BYTE_3
                or data[cls.EXPECTED_PROTOCOL_BYTE_4_POSITION] != cls.EXPECTED_PROTOCOL_BYTE_4
            ):
                return False

        return True

    @classmethod
    def _remove_protocol_bytes(cls, data: bytes) -> tuple[bytes, Optional[bytes]]:
        """
        Remove the protocol bytes from the data and returns the advertisement data and the scan
        response data in a tuple. The scan response data is optional and may be None if not present.
        """
        adv = data[cls.SLICE_ADVERTISEMENT]
        scan_response = None

        if len(data) > 22:
            scan_response = data[cls.SLICE_SCAN_RESPONSE]

        return (adv, scan_response)

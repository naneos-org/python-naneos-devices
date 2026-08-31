from typing import Optional

from bleak.backends.scanner import AdvertisementData

from naneos.logger import LEVEL_WARNING, get_naneos_logger

logger = get_naneos_logger(__name__, LEVEL_WARNING)


class PartectorBleDecoder:
    """
    Decode the BLE data from the Partector device.
    """

    VALID_DATA_LENGTHS = {22, 44}

    # One frame: protocol byte, 20 payload bytes, protocol byte.
    FRAME_LENGTH = 22

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

    @classmethod
    def _get_adv_bytes(cls, adv: AdvertisementData) -> bytes:
        """
        Returns the full advertisement data from the Partector device.
        We are violating the BLE standard here by using the manufacturer data field for our own purposes.
        This is not a good practice, but it was the only way to put more data into the advertisement.

        Because the two protocol bytes end up in the manufacturer id, almost every
        frame arrives under a different id. BlueZ merges those into one map and
        never evicts an entry, so manufacturer_data holds every frame seen from
        the device, not the current one. Picking the first entry therefore froze
        the reading at the oldest frame, and returned nothing at all whenever that
        frame happened to be a scan response.

        Frames are selected by their protocol byte instead, keeping the last of
        each kind: the advertisement ("X") and the scan response ("Y"), which the
        caller expects concatenated. Insertion order is the only ordering the map
        offers, so "last" is a best effort - an id that repeats keeps its original
        position while its payload is updated in place.
        """
        newest_adv = b""
        newest_scan_response = b""

        for manufacturer_id, payload in adv.manufacturer_data.items():
            frame = manufacturer_id.to_bytes(2, "little") + payload

            # Backends that hand over advertisement and scan response already
            # concatenated are split here, so both halves take the same path.
            if len(frame) == 2 * cls.FRAME_LENGTH:
                frames = [frame[: cls.FRAME_LENGTH], frame[cls.FRAME_LENGTH :]]
            else:
                frames = [frame]

            for candidate in frames:
                if (
                    len(candidate) != cls.FRAME_LENGTH
                    or candidate[-1] != cls.EXPECTED_PROTOCOL_BYTE_2
                ):
                    continue

                if candidate[0] == cls.EXPECTED_PROTOCOL_BYTE_1:
                    newest_adv = candidate
                elif candidate[0] == cls.EXPECTED_PROTOCOL_BYTE_3:
                    newest_scan_response = candidate

        return newest_adv + newest_scan_response

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

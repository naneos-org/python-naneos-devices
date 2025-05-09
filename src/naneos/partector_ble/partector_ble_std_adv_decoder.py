from naneos.logger import LEVEL_INFO, get_naneos_logger

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleStdAdvDecoder:
    """
    Decode the advertisement data from the Partector device.
    """

    OFFSET_SERIAL_NUMBER = slice(15, 17)

    @classmethod
    def get_serial_number(cls, data: bytes) -> int:
        """
        Get the serial number from the advertisement data.
        """
        return int.from_bytes(data[cls.OFFSET_SERIAL_NUMBER], byteorder="little")

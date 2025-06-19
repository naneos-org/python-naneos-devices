from typing import Optional

from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint
from naneos.partector_ble.decoder.partector_ble_decoder_blueprint import (
    PartectorBleDecoderBlueprint,
)


class PartectorBleDecoderSize(PartectorBleDecoderBlueprint):
    """
    Decode the std advertisement data from the Partector device.
    """

    # == External used methods =====================================================================
    @classmethod
    def decode(
        cls, data: bytes, data_structure: Optional[NaneosDeviceDataPoint] = None
    ) -> NaneosDeviceDataPoint:
        """
        Decode the auxiliary characteristic data from the Partector device.
        """
        decoded_data = NaneosDeviceDataPoint(
            particle_number_10nm=cls._get_10nm(data),
            particle_number_16nm=cls._get_10nm(data),
            particle_number_26nm=cls._get_26nm(data),
            particle_number_43nm=cls._get_43nm(data),
            particle_number_70nm=cls._get_70nm(data),
            particle_number_114nm=cls._get_114nm(data),
            particle_number_185nm=cls._get_185nm(data),
            particle_number_300nm=cls._get_300nm(data),
        )

        if not data_structure:
            return decoded_data

        # Fill the given data_structure with the decoded data
        for field in NaneosDeviceDataPoint.BLE_SIZE_DIST_FIELD_NAMES:
            setattr(data_structure, field, getattr(decoded_data, field))
        return data_structure

    # == Helpers ===================================================================================
    @staticmethod
    def _get_10nm(data: bytes) -> float:
        """
        Get the 10nm value from the size characteristic data.
        """
        val = float(
            int.from_bytes(bytearray([data[0], data[1], data[2] & 0x0F]), byteorder="little")
        )
        return val

    @staticmethod
    def _get_16nm(data: bytes) -> float:
        """
        Get the 16nm value from the size characteristic data.
        """
        val = float(
            int.from_bytes(bytearray([data[2] & 0xF0, data[3], data[4]]), byteorder="little") >> 4
        )
        return val

    @staticmethod
    def _get_26nm(data: bytes) -> float:
        """
        Get the 26nm value from the size characteristic data.
        """
        val = float(
            int.from_bytes(bytearray([data[5], data[6], data[7] & 0x0F]), byteorder="little")
        )
        return val

    @staticmethod
    def _get_43nm(data: bytes) -> float:
        """
        Get the 43nm value from the size characteristic data.
        """
        val = float(
            int.from_bytes(bytearray([data[7] & 0xF0, data[8], data[9]]), byteorder="little") >> 4
        )
        return val

    @staticmethod
    def _get_70nm(data: bytes) -> float:
        """
        Get the 70nm value from the size characteristic data.
        """
        val = float(
            int.from_bytes(bytearray([data[10], data[11], data[12] & 0x0F]), byteorder="little")
        )
        return val

    @staticmethod
    def _get_114nm(data: bytes) -> float:
        """
        Get the 114nm value from the size characteristic data.
        """
        val = float(
            int.from_bytes(bytearray([data[12] & 0xF0, data[13], data[14]]), byteorder="little")
            >> 4
        )
        return val

    @staticmethod
    def _get_185nm(data: bytes) -> float:
        """
        Get the 185nm value from the size characteristic data.
        """
        val = float(
            int.from_bytes(bytearray([data[15], data[16], data[17] & 0x0F]), byteorder="little")
        )
        return val

    @staticmethod
    def _get_300nm(data: bytes) -> float:
        """
        Get the 300nm value from the size characteristic data.
        """
        val = float(
            int.from_bytes(bytearray([data[17] & 0xF0, data[18], data[19]]), byteorder="little")
            >> 4
        )
        return val

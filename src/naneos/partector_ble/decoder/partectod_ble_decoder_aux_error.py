from typing import Optional

from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint
from naneos.partector_ble.decoder.partector_ble_decoder_blueprint import (
    PartectorBleDecoderBlueprint,
)


class PartectorBleDecoderAuxError(PartectorBleDecoderBlueprint):
    """
    Decode the std advertisement data from the Partector device.
    """

    OFFSET_ERROR = slice(2, 6)
    OFFSET_IDIFF_DELAY_ON = slice(6, 7)
    OFFSET_IDIFF_DELAY_OFF = slice(7, 8)
    OFFSET_IDIFF_AVERAGE = slice(8, 10)
    OFFSET_IDIFF_STDV = slice(10, 12)
    OFFSET_IDIFF_MAX = slice(12, 14)
    OFFSET_UCOR_ONSET = slice(14, 16)

    FACTOR_DIFFUSION_CURRENT = 0.01

    # == External used methods =====================================================================
    @classmethod
    def decode(
        cls, data: bytes, data_structure: Optional[NaneosDeviceDataPoint] = None
    ) -> NaneosDeviceDataPoint:
        """
        Decode the auxiliary characteristic data from the Partector device.
        """
        decoded_data = NaneosDeviceDataPoint(
            device_status=cls._get_error(data),
            diffusion_current_delay_on=cls._get_idiff_delay_on(data),
            diffusion_current_delay_off=cls._get_idiff_delay_off(data),
            diffusion_current_average=cls._get_idiff_average(data),
            diffusion_current_stddev=cls._get_idiff_stddev(data),
            diffusion_current_max=cls._get_idiff_max(data),
            corona_voltage_onset=cls._get_ucor_onset(data),
        )

        if not data_structure:
            return decoded_data

        # Fill the given data_structure with the decoded data
        for field in NaneosDeviceDataPoint.BLE_AUX_ERROR_FIELD_NAMES:
            setattr(data_structure, field, getattr(decoded_data, field))
        return data_structure

    # == Helpers ===================================================================================
    @classmethod
    def _get_error(cls, data: bytes) -> int:
        """
        Get the error bits from the advertisement data.
        """
        val = int.from_bytes(data[cls.OFFSET_ERROR], byteorder="little")
        return val

    @classmethod
    def _get_idiff_delay_on(cls, data: bytes) -> int:
        """
        Get the diffusion current delay on from the advertisement data.
        """
        val = int.from_bytes(data[cls.OFFSET_IDIFF_DELAY_ON], byteorder="little")
        return val

    @classmethod
    def _get_idiff_delay_off(cls, data: bytes) -> int:
        """
        Get the diffusion current delay off from the advertisement data.
        """
        val = int.from_bytes(data[cls.OFFSET_IDIFF_DELAY_OFF], byteorder="little")
        return val

    @classmethod
    def _get_idiff_average(cls, data: bytes) -> float:
        """
        Get the diffusion current average from the advertisement data.
        """
        val = int.from_bytes(data[cls.OFFSET_IDIFF_AVERAGE], byteorder="little")
        return val * cls.FACTOR_DIFFUSION_CURRENT

    @classmethod
    def _get_idiff_stddev(cls, data: bytes) -> float:
        """
        Get the diffusion current standard deviation from the advertisement data.
        """
        val = int.from_bytes(data[cls.OFFSET_IDIFF_STDV], byteorder="little")
        return val * cls.FACTOR_DIFFUSION_CURRENT

    @classmethod
    def _get_idiff_max(cls, data: bytes) -> float:
        """
        Get the diffusion current maximum from the advertisement data.
        """
        val = int.from_bytes(data[cls.OFFSET_IDIFF_MAX], byteorder="little")
        return val * cls.FACTOR_DIFFUSION_CURRENT

    @classmethod
    def _get_ucor_onset(cls, data: bytes) -> int:
        """
        Get the corona voltage onset from the advertisement data.
        """
        val = int.from_bytes(data[cls.OFFSET_UCOR_ONSET], byteorder="little")
        return val

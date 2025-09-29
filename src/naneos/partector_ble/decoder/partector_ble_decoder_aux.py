from typing import Optional

from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint
from naneos.partector_ble.decoder.partector_ble_decoder_blueprint import (
    PartectorBleDecoderBlueprint,
)


class PartectorBleDecoderAux(PartectorBleDecoderBlueprint):
    """
    Decode the std advertisement data from the Partector device.
    """

    OFFSET_CORONA_VOLTAGE = slice(0, 2)
    OFFSET_DIFFUSION_CURRENT = slice(2, 4)
    OFFSET_DEPOSITION_VOLTAGE = slice(4, 6)
    OFFSET_FLOW_FROM_DP = slice(6, 8)
    OFFSET_AMBIENT_PRESSURE = slice(8, 10)
    OFFSET_EM_AMPLITUDE_1 = slice(10, 12)
    OFFSET_EM_AMPLITUDE_2 = slice(12, 14)
    OFFSET_EM_GAIN_1 = slice(14, 16)
    OFFSET_EM_GAIN_2 = slice(16, 18)
    OFFSET_DIFFUSION_CURRENT_OFFSET = slice(18, 20)

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
            corona_voltage=cls._get_corona_voltage(data),
            diffusion_current=cls._get_diffusion_current(data),
            deposition_voltage=cls._get_deposition_voltage(data),
            flow_from_dp=cls._get_flow_from_dp(data),
            ambient_pressure=cls._get_ambient_pressure(data),
            electrometer_1_amplitude=cls._get_em_amplitude_1(data),
            electrometer_2_amplitude=cls._get_em_amplitude_2(data),
            electrometer_1_gain=cls._get_em_gain_1(data),
            electrometer_2_gain=cls._get_em_gain_2(data),
            diffusion_current_offset=cls._get_diffusion_current_offset(data),
        )

        if not data_structure:
            return decoded_data

        # Fill the given data_structure with the decoded data
        for field in NaneosDeviceDataPoint.BLE_AUX_FIELD_NAMES:
            setattr(data_structure, field, getattr(decoded_data, field))
        return data_structure

    # == Helpers ===================================================================================
    @classmethod
    def _get_corona_voltage(cls, data: bytes) -> float:
        """
        Get the corona voltage from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_CORONA_VOLTAGE], byteorder="little"))
        return val

    @classmethod
    def _get_diffusion_current(cls, data: bytes) -> float:
        """
        Get the diffusion current from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_DIFFUSION_CURRENT], byteorder="little"))
        return val * cls.FACTOR_DIFFUSION_CURRENT

    @classmethod
    def _get_deposition_voltage(cls, data: bytes) -> float:
        """
        Get the deposition voltage from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_DEPOSITION_VOLTAGE], byteorder="little"))
        return val

    @classmethod
    def _get_flow_from_dp(cls, data: bytes) -> float:
        """
        Get the flow from DP from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_FLOW_FROM_DP], byteorder="little")) / 1000.0
        return val

    @classmethod
    def _get_ambient_pressure(cls, data: bytes) -> float:
        """
        Get the ambient pressure from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_AMBIENT_PRESSURE], byteorder="little"))
        return val

    @classmethod
    def _get_em_amplitude_1(cls, data: bytes) -> float:
        """
        Get the EM amplitude 1 from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_EM_AMPLITUDE_1], byteorder="little"))
        return val

    @classmethod
    def _get_em_amplitude_2(cls, data: bytes) -> float:
        """
        Get the EM amplitude 2 from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_EM_AMPLITUDE_2], byteorder="little"))
        return val

    @classmethod
    def _get_em_gain_1(cls, data: bytes) -> float:
        """
        Get the EM gain 1 from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_EM_GAIN_1], byteorder="little"))
        return val

    @classmethod
    def _get_em_gain_2(cls, data: bytes) -> float:
        """
        Get the EM gain 2 from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_EM_GAIN_2], byteorder="little"))
        return val

    @classmethod
    def _get_diffusion_current_offset(cls, data: bytes) -> float:
        """
        Get the diffusion current offset from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_DIFFUSION_CURRENT_OFFSET], byteorder="little"))
        return val

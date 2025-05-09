from typing import Optional

from naneos.logger import LEVEL_INFO, get_naneos_logger
from naneos.partector.blueprints._data_structure import Partector2DataStructure

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleStdAdvDecoder:
    """
    Decode the advertisement data from the Partector device.
    """

    OFFSET_SERIAL_NUMBER = slice(14, 16)

    OFFSET_DEVICE_STATE_1 = slice(10, 12)
    ELEMET_DEVICE_STATE_2 = 19

    OFFSET_LDSA = slice(0, 3)
    OFFSET_PARTICLE_DIAMETER = slice(3, 5)
    OFFSET_PARTICLE_NUMBER = slice(5, 8)
    OFFSET_TEMPERATURE = slice(8, 9)
    OFFSET_RELATIVE_HUMIDITY = slice(9, 10)
    OFFSET_BATTERY_VOLTAGE = slice(12, 14)
    OFFSET_PARTICLE_MASS = slice(14, 18)
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

    FACTOR_LDSA = 0.01
    FACTOR_BATTERY_VOLTAGE = 0.01
    FACTOR_PARTICLE_MASS = 0.01
    FACTOR_DIFFUSION_CURRENT = 0.01

    # == External used methods =====================================================================
    @classmethod
    def get_serial_number(cls, data: bytes) -> int:
        """
        Get the serial number from the advertisement data.
        """
        return int.from_bytes(data[cls.OFFSET_SERIAL_NUMBER], byteorder="little")

    @classmethod
    def decode_partector_advertised_data(
        cls, data: tuple[bytes, Optional[bytes]]
    ) -> Partector2DataStructure:
        """
        Decode the standard characteristic data from the Partector device.
        Also ads the aux characteristics if available.
        """
        data_structure = cls._decode_advertisement(data[0])
        if data[1]:
            aux = cls._decode_aux_characteristic(data[1])
            for field in Partector2DataStructure.AUX_FIELD_NAMES:
                setattr(data_structure, field, getattr(aux, field))

        return data_structure

    # == Helpers ===================================================================================
    @classmethod
    def _decode_advertisement(cls, data: bytes) -> Partector2DataStructure:
        """
        Decode the advertisement data from the Partector device.
        """
        decoded_data = Partector2DataStructure(
            serial_number=cls.get_serial_number(data),
            ldsa=cls._get_ldsa(data),
            particle_diameter=cls._get_diameter(data),
            particle_number=cls._get_particle_number(data),
            temperature=cls._get_temperature(data),
            relative_humidity=cls._get_relative_humidity(data),
            device_status=cls._get_device_state(data),
            battery_voltage=cls._get_battery_voltage(data),
            particle_mass=cls._get_particle_mass(data),
        )

        return decoded_data

    @classmethod
    def _decode_aux_characteristic(cls, data: bytes) -> Partector2DataStructure:
        """
        Decode the auxiliary characteristic data from the Partector device.
        """
        decoded_data = Partector2DataStructure(
            corona_voltage=cls._get_corona_voltage(data),
            diffusion_current=cls._get_diffusion_current(data),
            deposition_voltage=cls._get_deposition_voltage(data),
            flow_from_dp=cls._get_flow_from_dp(data),
            ambient_pressure=cls._get_ambient_pressure(data),
            em_amplitude1=cls._get_em_amplitude_1(data),
            em_amplitude2=cls._get_em_amplitude_2(data),
            em_gain1=cls._get_em_gain_1(data),
            em_gain2=cls._get_em_gain_2(data),
            diffusion_current_offset=cls._get_diffusion_current_offset(data),
        )

        return decoded_data

    @classmethod
    def _get_ldsa(cls, data: bytes) -> float:
        """
        Get the LDSA from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_LDSA], byteorder="little"))
        return val * cls.FACTOR_LDSA

    @classmethod
    def _get_diameter(cls, data: bytes) -> float:
        """
        Get the particle diameter from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_PARTICLE_DIAMETER], byteorder="little"))
        return val

    @classmethod
    def _get_particle_number(cls, data: bytes) -> float:
        """
        Get the particle number from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_PARTICLE_NUMBER], byteorder="little"))
        return val

    @classmethod
    def _get_temperature(cls, data: bytes) -> float:
        """
        Get the temperature from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_TEMPERATURE], byteorder="little"))
        return val

    @classmethod
    def _get_relative_humidity(cls, data: bytes) -> float:
        """
        Get the relative humidity from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_RELATIVE_HUMIDITY], byteorder="little"))
        return val

    @classmethod
    def _get_device_state(cls, data: bytes) -> int:
        """
        Get the device state from the advertisement data.
        """
        val = int.from_bytes(data[cls.OFFSET_DEVICE_STATE_1], byteorder="little")
        val += ((int(data[cls.ELEMET_DEVICE_STATE_2]) >> 1) & 0b01111111) << 16
        return val

    @classmethod
    def _get_battery_voltage(cls, data: bytes) -> float:
        """
        Get the battery voltage from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_BATTERY_VOLTAGE], byteorder="little"))
        return val * cls.FACTOR_BATTERY_VOLTAGE

    @classmethod
    def _get_particle_mass(cls, data: bytes) -> float:
        """
        Get the particle mass from the advertisement data.
        """
        val = float(int.from_bytes(data[cls.OFFSET_PARTICLE_MASS], byteorder="little"))
        return val * cls.FACTOR_PARTICLE_MASS

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
        val = float(int.from_bytes(data[cls.OFFSET_FLOW_FROM_DP], byteorder="little"))
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

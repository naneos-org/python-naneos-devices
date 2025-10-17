from typing import Optional

from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint
from naneos.partector_ble.decoder.partector_ble_decoder_blueprint import (
    PartectorBleDecoderBlueprint,
)


class PartectorBleDecoderStd(PartectorBleDecoderBlueprint):
    """
    Decode the std advertisement data from the Partector device.
    """

    OFFSET_SERIAL_NUMBER = slice(14, 16)

    OFFSET_DEVICE_STATE_1 = slice(10, 12)
    ELEMET_DEVICE_STATE_2 = 19

    OFFSET_LDSA = slice(0, 3)
    OFFSET_AVERAGE_PARTICLE_DIAMETER = slice(3, 5)
    OFFSET_PARTICLE_NUMBER = slice(5, 8)
    OFFSET_TEMPERATURE = slice(8, 9)
    OFFSET_RELATIVE_HUMIDITY = slice(9, 10)
    OFFSET_BATTERY_VOLTAGE = slice(12, 14)
    OFFSET_PARTICLE_MASS = slice(16, 19)

    FACTOR_LDSA = 0.01
    FACTOR_BATTERY_VOLTAGE = 0.01
    FACTOR_PARTICLE_MASS = 0.01

    # == External used methods =====================================================================
    @classmethod
    def get_serial_number(cls, data: bytes) -> int:
        """
        Get the serial number from the advertisement data.
        """
        return int.from_bytes(data[cls.OFFSET_SERIAL_NUMBER], byteorder="little")

    @classmethod
    def decode(
        cls, data: bytes, data_structure: Optional[NaneosDeviceDataPoint] = None
    ) -> NaneosDeviceDataPoint:
        """
        Decode the advertisement data from the Partector device.
        """
        decoded_data = NaneosDeviceDataPoint(
            serial_number=cls.get_serial_number(data),
            ldsa=cls._get_ldsa(data),
            average_particle_diameter=cls._get_diameter(data),
            particle_number_concentration=cls._get_particle_number(data),
            temperature=cls._get_temperature(data),
            relative_humidity=cls._get_relative_humidity(data),
            device_status=cls._get_device_state(data),
            battery_voltage=cls._get_battery_voltage(data),
            particle_mass=cls._get_particle_mass(data),
        )

        if not data_structure:
            return decoded_data

        # Fill the given data_structure with the decoded data
        for field in NaneosDeviceDataPoint.BLE_STD_FIELD_NAMES:
            setattr(data_structure, field, getattr(decoded_data, field))
        return data_structure

    # == Helpers ===================================================================================
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
        val = float(int.from_bytes(data[cls.OFFSET_AVERAGE_PARTICLE_DIAMETER], byteorder="little"))
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

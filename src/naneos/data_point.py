"""The measurement data point shared by the serial, BLE, upload and manager code."""

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class DeviceType(IntEnum):
    """Numeric device type as used by the upload backend. Do not renumber."""

    P2 = 0
    P1 = 1
    P2PRO = 2
    # 3 is reserved: it was the P2 Pro CS, which the backend still knows.


class ConnectionType(StrEnum):
    """How a data point reached us. Ordered by trust: serial > connected > advertisement."""

    SERIAL = "serial"
    CONNECTED = "connected"
    ADVERTISEMENT = "advertisement"


@dataclass
class NaneosDeviceDataPoint:
    """One measurement of one device. Every field is optional; None means "not reported"."""

    # Compatibility aliases for code written against naneos-devices <= 1.1.x.
    DEV_TYPE_P2 = DeviceType.P2
    DEV_TYPE_P1 = DeviceType.P1
    DEV_TYPE_P2PRO = DeviceType.P2PRO
    CONN_TYPE_SERIAL = ConnectionType.SERIAL
    CONN_TYPE_CONNECTED = ConnectionType.CONNECTED
    CONN_TYPE_ADVERTISEMENT = ConnectionType.ADVERTISEMENT

    # mandatory
    unix_timestamp: int | None = None  # ms since epoch
    serial_number: int | None = None
    connection_type: ConnectionType | None = None
    firmware_version: int | None = None
    device_type: DeviceType | None = None  # None until the device family is known
    device_status: int | None = None  # bitmask

    # optional
    runtime_min: float | None = None  # minutes since start
    ldsa: float | None = None  # um**2/cm**3
    particle_number_concentration: float | None = None  # particles/cm**3
    average_particle_diameter: float | None = None  # nm
    particle_mass: float | None = None  # ug/m**3
    particle_surface: float | None = None  # um**2/m**3
    diffusion_current: float | None = None  # nA
    diffusion_current_offset: float | None = None  # nA
    diffusion_current_average: float | None = None  # nA
    diffusion_current_stddev: float | None = None  # nA
    diffusion_current_max: float | None = None  # nA
    diffusion_current_delay_on: float | None = None  # centiseconds
    diffusion_current_delay_off: float | None = None  # centiseconds
    corona_voltage: float | None = None  # V
    corona_voltage_onset: float | None = None  # V
    hires_adc1: float | None = None  # instantaneous value electrometer 1
    hires_adc2: float | None = None  # instantaneous value electrometer 2
    electrometer_1_amplitude: float | None = None  # mV
    electrometer_2_amplitude: float | None = None  # mV
    electrometer_1_gain: float | None = None  # mV #TODO: check this unit
    electrometer_2_gain: float | None = None  # mV #TODO: check this unit
    temperature: float | None = None  # Celsius
    relative_humidity: float | None = None  # percent 0-100
    deposition_voltage: float | None = None  # V
    battery_voltage: float | None = None  # V
    flow_from_dp: float | None = None  # l/min
    ambient_pressure: float | None = None  # hPa
    channel_pressure: float | None = None  # hPa
    differential_pressure: float | None = None  # Pa
    pump_voltage: float | None = None  # V
    pump_current: float | None = None  # mA
    pump_pwm: float | None = None  # percent 0-100
    particle_number_10nm: float | None = None  # /cm^3/log(d)
    particle_number_16nm: float | None = None  # /cm^3/log(d)
    particle_number_26nm: float | None = None  # /cm^3/log(d)
    particle_number_43nm: float | None = None  # /cm^3/log(d)
    particle_number_70nm: float | None = None  # /cm^3/log(d)
    particle_number_114nm: float | None = None  # /cm^3/log(d)
    particle_number_185nm: float | None = None  # /cm^3/log(d)
    particle_number_300nm: float | None = None  # /cm^3/log(d)
    sigma_size_dist: float | None = None  # gsd
    steps_inversion: float | None = None  # steps count
    current_dist_0: float | None = None  # mV
    current_dist_1: float | None = None  # mV
    current_dist_2: float | None = None  # mV
    current_dist_3: float | None = None  # mV
    current_dist_4: float | None = None  # mV

    supply_voltage_5V: float | None = None  # V
    positive_voltage_3V3: float | None = None  # V
    negative_voltage_3V3: float | None = None  # V
    usb_cc_voltage: float | None = None  # V

    def to_dict(self, remove_nan: bool = True) -> dict[str, object]:
        """Field values by name; with remove_nan only the fields that are set."""
        values = {name: getattr(self, name) for name in self.__dataclass_fields__}
        if remove_nan:
            return {name: value for name, value in values.items() if value is not None}
        return values

    # -- DataFrame helpers, kept for compatibility. Prefer naneos.frames. ----------------------
    @staticmethod
    def to_pandas_df(points: list["NaneosDeviceDataPoint"]):
        from naneos.frames import to_pandas_df

        return to_pandas_df(points)

    @staticmethod
    def add_data_points_to_dict(devices: dict, points: list["NaneosDeviceDataPoint"]):
        from naneos.frames import add_data_points_to_dict

        return add_data_points_to_dict(devices, points)

    @staticmethod
    def add_data_point_to_dict(devices: dict, data: "NaneosDeviceDataPoint"):
        from naneos.frames import add_data_points_to_dict

        return add_data_points_to_dict(devices, [data])

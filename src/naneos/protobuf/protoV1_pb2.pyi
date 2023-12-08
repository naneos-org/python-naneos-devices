from typing import ClassVar as _ClassVar
from typing import Iterable as _Iterable
from typing import Mapping as _Mapping
from typing import Optional as _Optional
from typing import Union as _Union

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers

DESCRIPTOR: _descriptor.FileDescriptor

class CombinedData(_message.Message):
    __slots__ = ("abs_timestamp", "devices", "gateway_points", "position_points", "wind_points")
    ABS_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    DEVICES_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_POINTS_FIELD_NUMBER: _ClassVar[int]
    POSITION_POINTS_FIELD_NUMBER: _ClassVar[int]
    WIND_POINTS_FIELD_NUMBER: _ClassVar[int]
    abs_timestamp: int
    devices: _containers.RepeatedCompositeFieldContainer[Device]
    gateway_points: _containers.RepeatedCompositeFieldContainer[GatewayPoint]
    position_points: _containers.RepeatedCompositeFieldContainer[PositionPoint]
    wind_points: _containers.RepeatedCompositeFieldContainer[WindPoint]
    def __init__(
        self,
        abs_timestamp: _Optional[int] = ...,
        devices: _Optional[_Iterable[_Union[Device, _Mapping]]] = ...,
        gateway_points: _Optional[_Iterable[_Union[GatewayPoint, _Mapping]]] = ...,
        position_points: _Optional[_Iterable[_Union[PositionPoint, _Mapping]]] = ...,
        wind_points: _Optional[_Iterable[_Union[WindPoint, _Mapping]]] = ...,
    ) -> None: ...

class Device(_message.Message):
    __slots__ = ("type", "serial_number", "device_points")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SERIAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    DEVICE_POINTS_FIELD_NUMBER: _ClassVar[int]
    type: int
    serial_number: int
    device_points: _containers.RepeatedCompositeFieldContainer[DevicePoint]
    def __init__(
        self,
        type: _Optional[int] = ...,
        serial_number: _Optional[int] = ...,
        device_points: _Optional[_Iterable[_Union[DevicePoint, _Mapping]]] = ...,
    ) -> None: ...

class DevicePoint(_message.Message):
    __slots__ = (
        "timestamp",
        "device_status",
        "ldsa",
        "average_particle_diameter",
        "particle_number_concentration",
        "temperature",
        "relative_humidity",
        "battery_voltage",
        "particle_mass",
        "corona_voltage",
        "diffusion_current",
        "deposition_voltage",
        "flow",
        "ambient_pressure",
        "electrometer_offset",
        "electrometer_2_offset",
        "electrometer_gain",
        "electrometer_2_gain",
        "diffusion_current_offset",
        "particle_number_10nm",
        "particle_number_16nm",
        "particle_number_26nm",
        "particle_number_43nm",
        "particle_number_70nm",
        "particle_number_114nm",
        "particle_number_185nm",
        "particle_number_300nm",
        "surface",
        "sigma_size_dist",
        "steps_inversion",
        "current_dist_0",
        "current_dist_1",
        "current_dist_2",
        "current_dist_3",
        "current_dist_4",
        "pump_current",
        "pump_pwm",
        "cs_status",
    )
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    DEVICE_STATUS_FIELD_NUMBER: _ClassVar[int]
    LDSA_FIELD_NUMBER: _ClassVar[int]
    AVERAGE_PARTICLE_DIAMETER_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_CONCENTRATION_FIELD_NUMBER: _ClassVar[int]
    TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    RELATIVE_HUMIDITY_FIELD_NUMBER: _ClassVar[int]
    BATTERY_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_MASS_FIELD_NUMBER: _ClassVar[int]
    CORONA_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    DIFFUSION_CURRENT_FIELD_NUMBER: _ClassVar[int]
    DEPOSITION_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    FLOW_FIELD_NUMBER: _ClassVar[int]
    AMBIENT_PRESSURE_FIELD_NUMBER: _ClassVar[int]
    ELECTROMETER_OFFSET_FIELD_NUMBER: _ClassVar[int]
    ELECTROMETER_2_OFFSET_FIELD_NUMBER: _ClassVar[int]
    ELECTROMETER_GAIN_FIELD_NUMBER: _ClassVar[int]
    ELECTROMETER_2_GAIN_FIELD_NUMBER: _ClassVar[int]
    DIFFUSION_CURRENT_OFFSET_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_10NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_16NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_26NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_43NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_70NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_114NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_185NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_300NM_FIELD_NUMBER: _ClassVar[int]
    SURFACE_FIELD_NUMBER: _ClassVar[int]
    SIGMA_SIZE_DIST_FIELD_NUMBER: _ClassVar[int]
    STEPS_INVERSION_FIELD_NUMBER: _ClassVar[int]
    CURRENT_DIST_0_FIELD_NUMBER: _ClassVar[int]
    CURRENT_DIST_1_FIELD_NUMBER: _ClassVar[int]
    CURRENT_DIST_2_FIELD_NUMBER: _ClassVar[int]
    CURRENT_DIST_3_FIELD_NUMBER: _ClassVar[int]
    CURRENT_DIST_4_FIELD_NUMBER: _ClassVar[int]
    PUMP_CURRENT_FIELD_NUMBER: _ClassVar[int]
    PUMP_PWM_FIELD_NUMBER: _ClassVar[int]
    CS_STATUS_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    device_status: int
    ldsa: int
    average_particle_diameter: int
    particle_number_concentration: int
    temperature: int
    relative_humidity: int
    battery_voltage: int
    particle_mass: int
    corona_voltage: int
    diffusion_current: int
    deposition_voltage: int
    flow: int
    ambient_pressure: int
    electrometer_offset: int
    electrometer_2_offset: int
    electrometer_gain: int
    electrometer_2_gain: int
    diffusion_current_offset: int
    particle_number_10nm: int
    particle_number_16nm: int
    particle_number_26nm: int
    particle_number_43nm: int
    particle_number_70nm: int
    particle_number_114nm: int
    particle_number_185nm: int
    particle_number_300nm: int
    surface: int
    sigma_size_dist: int
    steps_inversion: int
    current_dist_0: int
    current_dist_1: int
    current_dist_2: int
    current_dist_3: int
    current_dist_4: int
    pump_current: int
    pump_pwm: int
    cs_status: int
    def __init__(
        self,
        timestamp: _Optional[int] = ...,
        device_status: _Optional[int] = ...,
        ldsa: _Optional[int] = ...,
        average_particle_diameter: _Optional[int] = ...,
        particle_number_concentration: _Optional[int] = ...,
        temperature: _Optional[int] = ...,
        relative_humidity: _Optional[int] = ...,
        battery_voltage: _Optional[int] = ...,
        particle_mass: _Optional[int] = ...,
        corona_voltage: _Optional[int] = ...,
        diffusion_current: _Optional[int] = ...,
        deposition_voltage: _Optional[int] = ...,
        flow: _Optional[int] = ...,
        ambient_pressure: _Optional[int] = ...,
        electrometer_offset: _Optional[int] = ...,
        electrometer_2_offset: _Optional[int] = ...,
        electrometer_gain: _Optional[int] = ...,
        electrometer_2_gain: _Optional[int] = ...,
        diffusion_current_offset: _Optional[int] = ...,
        particle_number_10nm: _Optional[int] = ...,
        particle_number_16nm: _Optional[int] = ...,
        particle_number_26nm: _Optional[int] = ...,
        particle_number_43nm: _Optional[int] = ...,
        particle_number_70nm: _Optional[int] = ...,
        particle_number_114nm: _Optional[int] = ...,
        particle_number_185nm: _Optional[int] = ...,
        particle_number_300nm: _Optional[int] = ...,
        surface: _Optional[int] = ...,
        sigma_size_dist: _Optional[int] = ...,
        steps_inversion: _Optional[int] = ...,
        current_dist_0: _Optional[int] = ...,
        current_dist_1: _Optional[int] = ...,
        current_dist_2: _Optional[int] = ...,
        current_dist_3: _Optional[int] = ...,
        current_dist_4: _Optional[int] = ...,
        pump_current: _Optional[int] = ...,
        pump_pwm: _Optional[int] = ...,
        cs_status: _Optional[int] = ...,
    ) -> None: ...

class GatewayPoint(_message.Message):
    __slots__ = (
        "timestamp",
        "serial_number",
        "firmware_version",
        "free_memory",
        "free_heap",
        "largest_free_block_heap",
        "cellular_signal",
        "battery_int_soc",
        "battery_ext_soc",
        "battery_ext_voltage",
        "charging_ext_voltage",
    )
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    SERIAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    FIRMWARE_VERSION_FIELD_NUMBER: _ClassVar[int]
    FREE_MEMORY_FIELD_NUMBER: _ClassVar[int]
    FREE_HEAP_FIELD_NUMBER: _ClassVar[int]
    LARGEST_FREE_BLOCK_HEAP_FIELD_NUMBER: _ClassVar[int]
    CELLULAR_SIGNAL_FIELD_NUMBER: _ClassVar[int]
    BATTERY_INT_SOC_FIELD_NUMBER: _ClassVar[int]
    BATTERY_EXT_SOC_FIELD_NUMBER: _ClassVar[int]
    BATTERY_EXT_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    CHARGING_EXT_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    serial_number: int
    firmware_version: int
    free_memory: int
    free_heap: int
    largest_free_block_heap: int
    cellular_signal: int
    battery_int_soc: int
    battery_ext_soc: int
    battery_ext_voltage: int
    charging_ext_voltage: int
    def __init__(
        self,
        timestamp: _Optional[int] = ...,
        serial_number: _Optional[int] = ...,
        firmware_version: _Optional[int] = ...,
        free_memory: _Optional[int] = ...,
        free_heap: _Optional[int] = ...,
        largest_free_block_heap: _Optional[int] = ...,
        cellular_signal: _Optional[int] = ...,
        battery_int_soc: _Optional[int] = ...,
        battery_ext_soc: _Optional[int] = ...,
        battery_ext_voltage: _Optional[int] = ...,
        charging_ext_voltage: _Optional[int] = ...,
    ) -> None: ...

class PositionPoint(_message.Message):
    __slots__ = ("timestamp", "latitude", "longitude")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    LATITUDE_FIELD_NUMBER: _ClassVar[int]
    LONGITUDE_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    latitude: float
    longitude: float
    def __init__(
        self,
        timestamp: _Optional[int] = ...,
        latitude: _Optional[float] = ...,
        longitude: _Optional[float] = ...,
    ) -> None: ...

class WindPoint(_message.Message):
    __slots__ = ("timestamp", "wind_speed", "wind_angle")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    WIND_SPEED_FIELD_NUMBER: _ClassVar[int]
    WIND_ANGLE_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    wind_speed: int
    wind_angle: int
    def __init__(
        self,
        timestamp: _Optional[int] = ...,
        wind_speed: _Optional[int] = ...,
        wind_angle: _Optional[int] = ...,
    ) -> None: ...

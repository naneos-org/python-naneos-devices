from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DeviceType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    P2: _ClassVar[DeviceType]
    P1: _ClassVar[DeviceType]
    P2_PRO: _ClassVar[DeviceType]
    P2_PRO_CS: _ClassVar[DeviceType]
    OLS: _ClassVar[DeviceType]
    P9: _ClassVar[DeviceType]

class UplinkType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MSOM_UPLINK: _ClassVar[UplinkType]
    TRACKER_UPLINK: _ClassVar[UplinkType]
P2: DeviceType
P1: DeviceType
P2_PRO: DeviceType
P2_PRO_CS: DeviceType
OLS: DeviceType
P9: DeviceType
MSOM_UPLINK: UplinkType
TRACKER_UPLINK: UplinkType
SCALE_FIELD_NUMBER: _ClassVar[int]
scale: _descriptor.FieldDescriptor
UNIT_FIELD_NUMBER: _ClassVar[int]
unit: _descriptor.FieldDescriptor

class UiCurve(_message.Message):
    __slots__ = ("type", "abs_timestamp", "serial_number", "U_values", "I_values")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ABS_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    SERIAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    U_VALUES_FIELD_NUMBER: _ClassVar[int]
    I_VALUES_FIELD_NUMBER: _ClassVar[int]
    type: DeviceType
    abs_timestamp: int
    serial_number: int
    U_values: _containers.RepeatedScalarFieldContainer[int]
    I_values: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, type: _Optional[_Union[DeviceType, str]] = ..., abs_timestamp: _Optional[int] = ..., serial_number: _Optional[int] = ..., U_values: _Optional[_Iterable[int]] = ..., I_values: _Optional[_Iterable[int]] = ...) -> None: ...

class PulseForm(_message.Message):
    __slots__ = ("type", "abs_timestamp", "serial_number", "I_values")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ABS_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    SERIAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    I_VALUES_FIELD_NUMBER: _ClassVar[int]
    type: DeviceType
    abs_timestamp: int
    serial_number: int
    I_values: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, type: _Optional[_Union[DeviceType, str]] = ..., abs_timestamp: _Optional[int] = ..., serial_number: _Optional[int] = ..., I_values: _Optional[_Iterable[int]] = ...) -> None: ...

class CombinedData(_message.Message):
    __slots__ = ("abs_timestamp", "devices", "uplink", "position_points")
    ABS_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    DEVICES_FIELD_NUMBER: _ClassVar[int]
    UPLINK_FIELD_NUMBER: _ClassVar[int]
    POSITION_POINTS_FIELD_NUMBER: _ClassVar[int]
    abs_timestamp: int
    devices: _containers.RepeatedCompositeFieldContainer[Device]
    uplink: Uplink
    position_points: _containers.RepeatedCompositeFieldContainer[PositionPoint]
    def __init__(self, abs_timestamp: _Optional[int] = ..., devices: _Optional[_Iterable[_Union[Device, _Mapping]]] = ..., uplink: _Optional[_Union[Uplink, _Mapping]] = ..., position_points: _Optional[_Iterable[_Union[PositionPoint, _Mapping]]] = ...) -> None: ...

class Device(_message.Message):
    __slots__ = ("type", "serial_number", "device_points")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SERIAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    DEVICE_POINTS_FIELD_NUMBER: _ClassVar[int]
    type: DeviceType
    serial_number: int
    device_points: _containers.RepeatedCompositeFieldContainer[DevicePoint]
    def __init__(self, type: _Optional[_Union[DeviceType, str]] = ..., serial_number: _Optional[int] = ..., device_points: _Optional[_Iterable[_Union[DevicePoint, _Mapping]]] = ...) -> None: ...

class UserPlanDataFast(_message.Message):
    __slots__ = ("ldsa", "average_particle_diameter", "particle_number_concentration", "particle_mass", "surface")
    LDSA_FIELD_NUMBER: _ClassVar[int]
    AVERAGE_PARTICLE_DIAMETER_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_CONCENTRATION_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_MASS_FIELD_NUMBER: _ClassVar[int]
    SURFACE_FIELD_NUMBER: _ClassVar[int]
    ldsa: int
    average_particle_diameter: int
    particle_number_concentration: int
    particle_mass: int
    surface: int
    def __init__(self, ldsa: _Optional[int] = ..., average_particle_diameter: _Optional[int] = ..., particle_number_concentration: _Optional[int] = ..., particle_mass: _Optional[int] = ..., surface: _Optional[int] = ...) -> None: ...

class UserSizeDistData(_message.Message):
    __slots__ = ("particle_number_10nm", "particle_number_16nm", "particle_number_26nm", "particle_number_43nm", "particle_number_70nm", "particle_number_114nm", "particle_number_185nm", "particle_number_300nm")
    PARTICLE_NUMBER_10NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_16NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_26NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_43NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_70NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_114NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_185NM_FIELD_NUMBER: _ClassVar[int]
    PARTICLE_NUMBER_300NM_FIELD_NUMBER: _ClassVar[int]
    particle_number_10nm: int
    particle_number_16nm: int
    particle_number_26nm: int
    particle_number_43nm: int
    particle_number_70nm: int
    particle_number_114nm: int
    particle_number_185nm: int
    particle_number_300nm: int
    def __init__(self, particle_number_10nm: _Optional[int] = ..., particle_number_16nm: _Optional[int] = ..., particle_number_26nm: _Optional[int] = ..., particle_number_43nm: _Optional[int] = ..., particle_number_70nm: _Optional[int] = ..., particle_number_114nm: _Optional[int] = ..., particle_number_185nm: _Optional[int] = ..., particle_number_300nm: _Optional[int] = ...) -> None: ...

class StatusDataSizeDist(_message.Message):
    __slots__ = ("sigma_size_dist", "steps_inversion", "current_dist_0", "current_dist_1", "current_dist_2", "current_dist_3", "current_dist_4")
    SIGMA_SIZE_DIST_FIELD_NUMBER: _ClassVar[int]
    STEPS_INVERSION_FIELD_NUMBER: _ClassVar[int]
    CURRENT_DIST_0_FIELD_NUMBER: _ClassVar[int]
    CURRENT_DIST_1_FIELD_NUMBER: _ClassVar[int]
    CURRENT_DIST_2_FIELD_NUMBER: _ClassVar[int]
    CURRENT_DIST_3_FIELD_NUMBER: _ClassVar[int]
    CURRENT_DIST_4_FIELD_NUMBER: _ClassVar[int]
    sigma_size_dist: int
    steps_inversion: int
    current_dist_0: int
    current_dist_1: int
    current_dist_2: int
    current_dist_3: int
    current_dist_4: int
    def __init__(self, sigma_size_dist: _Optional[int] = ..., steps_inversion: _Optional[int] = ..., current_dist_0: _Optional[int] = ..., current_dist_1: _Optional[int] = ..., current_dist_2: _Optional[int] = ..., current_dist_3: _Optional[int] = ..., current_dist_4: _Optional[int] = ...) -> None: ...

class StatusDataSlow(_message.Message):
    __slots__ = ("device_status", "temperature", "relative_humidity", "battery_voltage", "corona_voltage", "diffusion_current", "deposition_voltage", "flow", "ambient_pressure", "electrometer_offset", "electrometer_2_offset", "electrometer_gain", "electrometer_2_gain", "diffusion_current_offset", "pump_current", "pump_pwm", "cs_status", "diffusion_current_stddev", "diffusion_current_delay_on", "diffusion_current_delay_off", "pump_voltage", "differential_pressure", "channel_pressure", "supply_voltage_5V", "positive_voltage_3V3", "negative_voltage_3V3", "usb_cc_voltage", "firmware_version", "diffusion_current_max", "diffusion_current_avg", "electrometer_amplitude", "electrometer_amplitude_2")
    DEVICE_STATUS_FIELD_NUMBER: _ClassVar[int]
    TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    RELATIVE_HUMIDITY_FIELD_NUMBER: _ClassVar[int]
    BATTERY_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
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
    PUMP_CURRENT_FIELD_NUMBER: _ClassVar[int]
    PUMP_PWM_FIELD_NUMBER: _ClassVar[int]
    CS_STATUS_FIELD_NUMBER: _ClassVar[int]
    DIFFUSION_CURRENT_STDDEV_FIELD_NUMBER: _ClassVar[int]
    DIFFUSION_CURRENT_DELAY_ON_FIELD_NUMBER: _ClassVar[int]
    DIFFUSION_CURRENT_DELAY_OFF_FIELD_NUMBER: _ClassVar[int]
    PUMP_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    DIFFERENTIAL_PRESSURE_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_PRESSURE_FIELD_NUMBER: _ClassVar[int]
    SUPPLY_VOLTAGE_5V_FIELD_NUMBER: _ClassVar[int]
    POSITIVE_VOLTAGE_3V3_FIELD_NUMBER: _ClassVar[int]
    NEGATIVE_VOLTAGE_3V3_FIELD_NUMBER: _ClassVar[int]
    USB_CC_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    FIRMWARE_VERSION_FIELD_NUMBER: _ClassVar[int]
    DIFFUSION_CURRENT_MAX_FIELD_NUMBER: _ClassVar[int]
    DIFFUSION_CURRENT_AVG_FIELD_NUMBER: _ClassVar[int]
    ELECTROMETER_AMPLITUDE_FIELD_NUMBER: _ClassVar[int]
    ELECTROMETER_AMPLITUDE_2_FIELD_NUMBER: _ClassVar[int]
    device_status: int
    temperature: int
    relative_humidity: int
    battery_voltage: int
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
    pump_current: int
    pump_pwm: int
    cs_status: int
    diffusion_current_stddev: int
    diffusion_current_delay_on: int
    diffusion_current_delay_off: int
    pump_voltage: int
    differential_pressure: int
    channel_pressure: int
    supply_voltage_5V: int
    positive_voltage_3V3: int
    negative_voltage_3V3: int
    usb_cc_voltage: int
    firmware_version: int
    diffusion_current_max: int
    diffusion_current_avg: int
    electrometer_amplitude: int
    electrometer_amplitude_2: int
    def __init__(self, device_status: _Optional[int] = ..., temperature: _Optional[int] = ..., relative_humidity: _Optional[int] = ..., battery_voltage: _Optional[int] = ..., corona_voltage: _Optional[int] = ..., diffusion_current: _Optional[int] = ..., deposition_voltage: _Optional[int] = ..., flow: _Optional[int] = ..., ambient_pressure: _Optional[int] = ..., electrometer_offset: _Optional[int] = ..., electrometer_2_offset: _Optional[int] = ..., electrometer_gain: _Optional[int] = ..., electrometer_2_gain: _Optional[int] = ..., diffusion_current_offset: _Optional[int] = ..., pump_current: _Optional[int] = ..., pump_pwm: _Optional[int] = ..., cs_status: _Optional[int] = ..., diffusion_current_stddev: _Optional[int] = ..., diffusion_current_delay_on: _Optional[int] = ..., diffusion_current_delay_off: _Optional[int] = ..., pump_voltage: _Optional[int] = ..., differential_pressure: _Optional[int] = ..., channel_pressure: _Optional[int] = ..., supply_voltage_5V: _Optional[int] = ..., positive_voltage_3V3: _Optional[int] = ..., negative_voltage_3V3: _Optional[int] = ..., usb_cc_voltage: _Optional[int] = ..., firmware_version: _Optional[int] = ..., diffusion_current_max: _Optional[int] = ..., diffusion_current_avg: _Optional[int] = ..., electrometer_amplitude: _Optional[int] = ..., electrometer_amplitude_2: _Optional[int] = ...) -> None: ...

class DevicePoint(_message.Message):
    __slots__ = ("timestamp", "user_plan_data", "user_size_dist_data", "status_data", "status_data_size_dist")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    USER_PLAN_DATA_FIELD_NUMBER: _ClassVar[int]
    USER_SIZE_DIST_DATA_FIELD_NUMBER: _ClassVar[int]
    STATUS_DATA_FIELD_NUMBER: _ClassVar[int]
    STATUS_DATA_SIZE_DIST_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    user_plan_data: UserPlanDataFast
    user_size_dist_data: UserSizeDistData
    status_data: StatusDataSlow
    status_data_size_dist: StatusDataSizeDist
    def __init__(self, timestamp: _Optional[int] = ..., user_plan_data: _Optional[_Union[UserPlanDataFast, _Mapping]] = ..., user_size_dist_data: _Optional[_Union[UserSizeDistData, _Mapping]] = ..., status_data: _Optional[_Union[StatusDataSlow, _Mapping]] = ..., status_data_size_dist: _Optional[_Union[StatusDataSizeDist, _Mapping]] = ...) -> None: ...

class Uplink(_message.Message):
    __slots__ = ("type", "serial_number", "uplink_points")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SERIAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    UPLINK_POINTS_FIELD_NUMBER: _ClassVar[int]
    type: UplinkType
    serial_number: int
    uplink_points: _containers.RepeatedCompositeFieldContainer[UplinkPoint]
    def __init__(self, type: _Optional[_Union[UplinkType, str]] = ..., serial_number: _Optional[int] = ..., uplink_points: _Optional[_Iterable[_Union[UplinkPoint, _Mapping]]] = ...) -> None: ...

class UplinkMeasurements(_message.Message):
    __slots__ = ("battery_int_voltage", "free_memory")
    BATTERY_INT_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    FREE_MEMORY_FIELD_NUMBER: _ClassVar[int]
    battery_int_voltage: int
    free_memory: int
    def __init__(self, battery_int_voltage: _Optional[int] = ..., free_memory: _Optional[int] = ...) -> None: ...

class UplinkSensors(_message.Message):
    __slots__ = ("sht_int_temperature", "sht_int_humidity", "sht_ext1_temperature", "sht_ext1_humidity", "sht_ext2_temperature", "sht_ext2_humidity", "sps30_pm1_0", "sps30_pm2_5", "sps30_pm4_0", "sps30_pm10_0", "sps30_nc0_5", "sps30_nc1_0", "sps30_nc2_5", "sps30_nc4_0", "sps30_nc10_0", "sps30_typical_particle_size", "wind_speed", "wind_gust", "wind_east", "wind_north", "mag_heading")
    SHT_INT_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    SHT_INT_HUMIDITY_FIELD_NUMBER: _ClassVar[int]
    SHT_EXT1_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    SHT_EXT1_HUMIDITY_FIELD_NUMBER: _ClassVar[int]
    SHT_EXT2_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    SHT_EXT2_HUMIDITY_FIELD_NUMBER: _ClassVar[int]
    SPS30_PM1_0_FIELD_NUMBER: _ClassVar[int]
    SPS30_PM2_5_FIELD_NUMBER: _ClassVar[int]
    SPS30_PM4_0_FIELD_NUMBER: _ClassVar[int]
    SPS30_PM10_0_FIELD_NUMBER: _ClassVar[int]
    SPS30_NC0_5_FIELD_NUMBER: _ClassVar[int]
    SPS30_NC1_0_FIELD_NUMBER: _ClassVar[int]
    SPS30_NC2_5_FIELD_NUMBER: _ClassVar[int]
    SPS30_NC4_0_FIELD_NUMBER: _ClassVar[int]
    SPS30_NC10_0_FIELD_NUMBER: _ClassVar[int]
    SPS30_TYPICAL_PARTICLE_SIZE_FIELD_NUMBER: _ClassVar[int]
    WIND_SPEED_FIELD_NUMBER: _ClassVar[int]
    WIND_GUST_FIELD_NUMBER: _ClassVar[int]
    WIND_EAST_FIELD_NUMBER: _ClassVar[int]
    WIND_NORTH_FIELD_NUMBER: _ClassVar[int]
    MAG_HEADING_FIELD_NUMBER: _ClassVar[int]
    sht_int_temperature: int
    sht_int_humidity: int
    sht_ext1_temperature: int
    sht_ext1_humidity: int
    sht_ext2_temperature: int
    sht_ext2_humidity: int
    sps30_pm1_0: int
    sps30_pm2_5: int
    sps30_pm4_0: int
    sps30_pm10_0: int
    sps30_nc0_5: int
    sps30_nc1_0: int
    sps30_nc2_5: int
    sps30_nc4_0: int
    sps30_nc10_0: int
    sps30_typical_particle_size: int
    wind_speed: int
    wind_gust: int
    wind_east: int
    wind_north: int
    mag_heading: int
    def __init__(self, sht_int_temperature: _Optional[int] = ..., sht_int_humidity: _Optional[int] = ..., sht_ext1_temperature: _Optional[int] = ..., sht_ext1_humidity: _Optional[int] = ..., sht_ext2_temperature: _Optional[int] = ..., sht_ext2_humidity: _Optional[int] = ..., sps30_pm1_0: _Optional[int] = ..., sps30_pm2_5: _Optional[int] = ..., sps30_pm4_0: _Optional[int] = ..., sps30_pm10_0: _Optional[int] = ..., sps30_nc0_5: _Optional[int] = ..., sps30_nc1_0: _Optional[int] = ..., sps30_nc2_5: _Optional[int] = ..., sps30_nc4_0: _Optional[int] = ..., sps30_nc10_0: _Optional[int] = ..., sps30_typical_particle_size: _Optional[int] = ..., wind_speed: _Optional[int] = ..., wind_gust: _Optional[int] = ..., wind_east: _Optional[int] = ..., wind_north: _Optional[int] = ..., mag_heading: _Optional[int] = ...) -> None: ...

class UplinkPower(_message.Message):
    __slots__ = ("solar_voltage", "battery_ext_voltage", "battery_ext_charge_mah", "battery_ext_discharge_mah", "battery_ext_temperature", "battery_ext_soc")
    SOLAR_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    BATTERY_EXT_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    BATTERY_EXT_CHARGE_MAH_FIELD_NUMBER: _ClassVar[int]
    BATTERY_EXT_DISCHARGE_MAH_FIELD_NUMBER: _ClassVar[int]
    BATTERY_EXT_TEMPERATURE_FIELD_NUMBER: _ClassVar[int]
    BATTERY_EXT_SOC_FIELD_NUMBER: _ClassVar[int]
    solar_voltage: int
    battery_ext_voltage: int
    battery_ext_charge_mah: int
    battery_ext_discharge_mah: int
    battery_ext_temperature: int
    battery_ext_soc: int
    def __init__(self, solar_voltage: _Optional[int] = ..., battery_ext_voltage: _Optional[int] = ..., battery_ext_charge_mah: _Optional[int] = ..., battery_ext_discharge_mah: _Optional[int] = ..., battery_ext_temperature: _Optional[int] = ..., battery_ext_soc: _Optional[int] = ...) -> None: ...

class UplinkPoint(_message.Message):
    __slots__ = ("timestamp", "uplink_measurements", "uplink_sensors", "uplink_power")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    UPLINK_MEASUREMENTS_FIELD_NUMBER: _ClassVar[int]
    UPLINK_SENSORS_FIELD_NUMBER: _ClassVar[int]
    UPLINK_POWER_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    uplink_measurements: UplinkMeasurements
    uplink_sensors: UplinkSensors
    uplink_power: UplinkPower
    def __init__(self, timestamp: _Optional[int] = ..., uplink_measurements: _Optional[_Union[UplinkMeasurements, _Mapping]] = ..., uplink_sensors: _Optional[_Union[UplinkSensors, _Mapping]] = ..., uplink_power: _Optional[_Union[UplinkPower, _Mapping]] = ...) -> None: ...

class PositionPoint(_message.Message):
    __slots__ = ("timestamp", "latitude", "longitude", "vertical_accuracy")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    LATITUDE_FIELD_NUMBER: _ClassVar[int]
    LONGITUDE_FIELD_NUMBER: _ClassVar[int]
    VERTICAL_ACCURACY_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    latitude: int
    longitude: int
    vertical_accuracy: int
    def __init__(self, timestamp: _Optional[int] = ..., latitude: _Optional[int] = ..., longitude: _Optional[int] = ..., vertical_accuracy: _Optional[int] = ...) -> None: ...

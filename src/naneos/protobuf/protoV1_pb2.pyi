from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class CombinedData(_message.Message):
    __slots__ = ("abs_timestamp", "devices", "gateway_points_legacy", "position_points", "wind_points", "uplink")
    ABS_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    DEVICES_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_POINTS_LEGACY_FIELD_NUMBER: _ClassVar[int]
    POSITION_POINTS_FIELD_NUMBER: _ClassVar[int]
    WIND_POINTS_FIELD_NUMBER: _ClassVar[int]
    UPLINK_FIELD_NUMBER: _ClassVar[int]
    abs_timestamp: int
    devices: _containers.RepeatedCompositeFieldContainer[Device]
    gateway_points_legacy: _containers.RepeatedCompositeFieldContainer[GatewayPointLegacy]
    position_points: _containers.RepeatedCompositeFieldContainer[PositionPoint]
    wind_points: _containers.RepeatedCompositeFieldContainer[WindPoint]
    uplink: Uplink
    def __init__(self, abs_timestamp: _Optional[int] = ..., devices: _Optional[_Iterable[_Union[Device, _Mapping]]] = ..., gateway_points_legacy: _Optional[_Iterable[_Union[GatewayPointLegacy, _Mapping]]] = ..., position_points: _Optional[_Iterable[_Union[PositionPoint, _Mapping]]] = ..., wind_points: _Optional[_Iterable[_Union[WindPoint, _Mapping]]] = ..., uplink: _Optional[_Union[Uplink, _Mapping]] = ...) -> None: ...

class Device(_message.Message):
    __slots__ = ("type", "serial_number", "device_points", "ui_curve")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SERIAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    DEVICE_POINTS_FIELD_NUMBER: _ClassVar[int]
    UI_CURVE_FIELD_NUMBER: _ClassVar[int]
    type: int
    serial_number: int
    device_points: _containers.RepeatedCompositeFieldContainer[DevicePoint]
    ui_curve: _containers.RepeatedCompositeFieldContainer[UiCurve]
    def __init__(self, type: _Optional[int] = ..., serial_number: _Optional[int] = ..., device_points: _Optional[_Iterable[_Union[DevicePoint, _Mapping]]] = ..., ui_curve: _Optional[_Iterable[_Union[UiCurve, _Mapping]]] = ...) -> None: ...

class DevicePoint(_message.Message):
    __slots__ = ("timestamp", "device_status", "ldsa", "average_particle_diameter", "particle_number_concentration", "temperature", "relative_humidity", "battery_voltage", "particle_mass", "corona_voltage", "diffusion_current", "deposition_voltage", "flow", "ambient_pressure", "electrometer_1_offset", "electrometer_2_offset", "electrometer_1_gain", "electrometer_2_gain", "diffusion_current_offset", "particle_number_10nm", "particle_number_16nm", "particle_number_26nm", "particle_number_43nm", "particle_number_70nm", "particle_number_114nm", "particle_number_185nm", "particle_number_300nm", "particle_surface", "sigma_size_dist", "steps_inversion", "current_dist_0", "current_dist_1", "current_dist_2", "current_dist_3", "current_dist_4", "pump_current", "pump_pwm", "cs_status", "diffusion_current_stddev", "diffusion_current_delay_on", "diffusion_current_delay_off", "pump_voltage", "differential_pressure", "channel_pressure", "supply_voltage_5V", "positive_voltage_3V3", "negative_voltage_3V3", "usb_cc_voltage", "firmware_version")
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
    ELECTROMETER_1_OFFSET_FIELD_NUMBER: _ClassVar[int]
    ELECTROMETER_2_OFFSET_FIELD_NUMBER: _ClassVar[int]
    ELECTROMETER_1_GAIN_FIELD_NUMBER: _ClassVar[int]
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
    PARTICLE_SURFACE_FIELD_NUMBER: _ClassVar[int]
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
    electrometer_1_offset: int
    electrometer_2_offset: int
    electrometer_1_gain: int
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
    particle_surface: int
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
    def __init__(self, timestamp: _Optional[int] = ..., device_status: _Optional[int] = ..., ldsa: _Optional[int] = ..., average_particle_diameter: _Optional[int] = ..., particle_number_concentration: _Optional[int] = ..., temperature: _Optional[int] = ..., relative_humidity: _Optional[int] = ..., battery_voltage: _Optional[int] = ..., particle_mass: _Optional[int] = ..., corona_voltage: _Optional[int] = ..., diffusion_current: _Optional[int] = ..., deposition_voltage: _Optional[int] = ..., flow: _Optional[int] = ..., ambient_pressure: _Optional[int] = ..., electrometer_1_offset: _Optional[int] = ..., electrometer_2_offset: _Optional[int] = ..., electrometer_1_gain: _Optional[int] = ..., electrometer_2_gain: _Optional[int] = ..., diffusion_current_offset: _Optional[int] = ..., particle_number_10nm: _Optional[int] = ..., particle_number_16nm: _Optional[int] = ..., particle_number_26nm: _Optional[int] = ..., particle_number_43nm: _Optional[int] = ..., particle_number_70nm: _Optional[int] = ..., particle_number_114nm: _Optional[int] = ..., particle_number_185nm: _Optional[int] = ..., particle_number_300nm: _Optional[int] = ..., particle_surface: _Optional[int] = ..., sigma_size_dist: _Optional[int] = ..., steps_inversion: _Optional[int] = ..., current_dist_0: _Optional[int] = ..., current_dist_1: _Optional[int] = ..., current_dist_2: _Optional[int] = ..., current_dist_3: _Optional[int] = ..., current_dist_4: _Optional[int] = ..., pump_current: _Optional[int] = ..., pump_pwm: _Optional[int] = ..., cs_status: _Optional[int] = ..., diffusion_current_stddev: _Optional[int] = ..., diffusion_current_delay_on: _Optional[int] = ..., diffusion_current_delay_off: _Optional[int] = ..., pump_voltage: _Optional[int] = ..., differential_pressure: _Optional[int] = ..., channel_pressure: _Optional[int] = ..., supply_voltage_5V: _Optional[int] = ..., positive_voltage_3V3: _Optional[int] = ..., negative_voltage_3V3: _Optional[int] = ..., usb_cc_voltage: _Optional[int] = ..., firmware_version: _Optional[int] = ...) -> None: ...

class UiCurve(_message.Message):
    __slots__ = ("timestamp", "U_values", "I_values")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    U_VALUES_FIELD_NUMBER: _ClassVar[int]
    I_VALUES_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    U_values: _containers.RepeatedScalarFieldContainer[int]
    I_values: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, timestamp: _Optional[int] = ..., U_values: _Optional[_Iterable[int]] = ..., I_values: _Optional[_Iterable[int]] = ...) -> None: ...

class Uplink(_message.Message):
    __slots__ = ("type", "serial_number", "uplink_points")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    SERIAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    UPLINK_POINTS_FIELD_NUMBER: _ClassVar[int]
    type: int
    serial_number: int
    uplink_points: _containers.RepeatedCompositeFieldContainer[UplinkPoint]
    def __init__(self, type: _Optional[int] = ..., serial_number: _Optional[int] = ..., uplink_points: _Optional[_Iterable[_Union[UplinkPoint, _Mapping]]] = ...) -> None: ...

class UplinkPoint(_message.Message):
    __slots__ = ("timestamp", "firmware_version", "device_status", "cellular_signal", "battery_int_voltage", "voltage_in", "usb_voltage_out", "usb_cc_voltage", "temperature_int", "relative_humidity_int", "temperature_ext_1", "relative_humidity_ext_1", "temperature_ext_2", "relative_humidity_ext_2", "sraw_voc", "voc_index", "ambient_pressure", "co2_ppm_1", "co2_ppm_2", "pm1_0_mass", "pm2_5_mass", "pm4_0_mass", "pm10_0_mass", "water_level_adc_percent")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    FIRMWARE_VERSION_FIELD_NUMBER: _ClassVar[int]
    DEVICE_STATUS_FIELD_NUMBER: _ClassVar[int]
    CELLULAR_SIGNAL_FIELD_NUMBER: _ClassVar[int]
    BATTERY_INT_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    VOLTAGE_IN_FIELD_NUMBER: _ClassVar[int]
    USB_VOLTAGE_OUT_FIELD_NUMBER: _ClassVar[int]
    USB_CC_VOLTAGE_FIELD_NUMBER: _ClassVar[int]
    TEMPERATURE_INT_FIELD_NUMBER: _ClassVar[int]
    RELATIVE_HUMIDITY_INT_FIELD_NUMBER: _ClassVar[int]
    TEMPERATURE_EXT_1_FIELD_NUMBER: _ClassVar[int]
    RELATIVE_HUMIDITY_EXT_1_FIELD_NUMBER: _ClassVar[int]
    TEMPERATURE_EXT_2_FIELD_NUMBER: _ClassVar[int]
    RELATIVE_HUMIDITY_EXT_2_FIELD_NUMBER: _ClassVar[int]
    SRAW_VOC_FIELD_NUMBER: _ClassVar[int]
    VOC_INDEX_FIELD_NUMBER: _ClassVar[int]
    AMBIENT_PRESSURE_FIELD_NUMBER: _ClassVar[int]
    CO2_PPM_1_FIELD_NUMBER: _ClassVar[int]
    CO2_PPM_2_FIELD_NUMBER: _ClassVar[int]
    PM1_0_MASS_FIELD_NUMBER: _ClassVar[int]
    PM2_5_MASS_FIELD_NUMBER: _ClassVar[int]
    PM4_0_MASS_FIELD_NUMBER: _ClassVar[int]
    PM10_0_MASS_FIELD_NUMBER: _ClassVar[int]
    WATER_LEVEL_ADC_PERCENT_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    firmware_version: int
    device_status: int
    cellular_signal: int
    battery_int_voltage: int
    voltage_in: int
    usb_voltage_out: int
    usb_cc_voltage: int
    temperature_int: int
    relative_humidity_int: int
    temperature_ext_1: int
    relative_humidity_ext_1: int
    temperature_ext_2: int
    relative_humidity_ext_2: int
    sraw_voc: int
    voc_index: int
    ambient_pressure: int
    co2_ppm_1: int
    co2_ppm_2: int
    pm1_0_mass: int
    pm2_5_mass: int
    pm4_0_mass: int
    pm10_0_mass: int
    water_level_adc_percent: int
    def __init__(self, timestamp: _Optional[int] = ..., firmware_version: _Optional[int] = ..., device_status: _Optional[int] = ..., cellular_signal: _Optional[int] = ..., battery_int_voltage: _Optional[int] = ..., voltage_in: _Optional[int] = ..., usb_voltage_out: _Optional[int] = ..., usb_cc_voltage: _Optional[int] = ..., temperature_int: _Optional[int] = ..., relative_humidity_int: _Optional[int] = ..., temperature_ext_1: _Optional[int] = ..., relative_humidity_ext_1: _Optional[int] = ..., temperature_ext_2: _Optional[int] = ..., relative_humidity_ext_2: _Optional[int] = ..., sraw_voc: _Optional[int] = ..., voc_index: _Optional[int] = ..., ambient_pressure: _Optional[int] = ..., co2_ppm_1: _Optional[int] = ..., co2_ppm_2: _Optional[int] = ..., pm1_0_mass: _Optional[int] = ..., pm2_5_mass: _Optional[int] = ..., pm4_0_mass: _Optional[int] = ..., pm10_0_mass: _Optional[int] = ..., water_level_adc_percent: _Optional[int] = ...) -> None: ...

class GatewayPointLegacy(_message.Message):
    __slots__ = ("timestamp", "serial_number", "firmware_version", "free_memory", "free_heap", "largest_free_block_heap", "cellular_signal", "battery_int_soc", "battery_ext_soc", "battery_ext_voltage", "charging_ext_voltage")
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
    def __init__(self, timestamp: _Optional[int] = ..., serial_number: _Optional[int] = ..., firmware_version: _Optional[int] = ..., free_memory: _Optional[int] = ..., free_heap: _Optional[int] = ..., largest_free_block_heap: _Optional[int] = ..., cellular_signal: _Optional[int] = ..., battery_int_soc: _Optional[int] = ..., battery_ext_soc: _Optional[int] = ..., battery_ext_voltage: _Optional[int] = ..., charging_ext_voltage: _Optional[int] = ...) -> None: ...

class PositionPoint(_message.Message):
    __slots__ = ("timestamp", "latitude", "longitude")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    LATITUDE_FIELD_NUMBER: _ClassVar[int]
    LONGITUDE_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    latitude: float
    longitude: float
    def __init__(self, timestamp: _Optional[int] = ..., latitude: _Optional[float] = ..., longitude: _Optional[float] = ...) -> None: ...

class WindPoint(_message.Message):
    __slots__ = ("timestamp", "wind_speed", "wind_angle")
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    WIND_SPEED_FIELD_NUMBER: _ClassVar[int]
    WIND_ANGLE_FIELD_NUMBER: _ClassVar[int]
    timestamp: int
    wind_speed: int
    wind_angle: int
    def __init__(self, timestamp: _Optional[int] = ..., wind_speed: _Optional[int] = ..., wind_angle: _Optional[int] = ...) -> None: ...

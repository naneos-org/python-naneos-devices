# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: protoV1.proto
# Protobuf Python Version: 4.25.0
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder

# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\rprotoV1.proto"\xb0\x01\n\x0c\x43ombinedData\x12\x15\n\rabs_timestamp\x18\x01 \x01(\r\x12\x18\n\x07\x64\x65vices\x18\x02 \x03(\x0b\x32\x07.Device\x12%\n\x0egateway_points\x18\x03 \x03(\x0b\x32\r.GatewayPoint\x12\'\n\x0fposition_points\x18\x04 \x03(\x0b\x32\x0e.PositionPoint\x12\x1f\n\x0bwind_points\x18\x05 \x03(\x0b\x32\n.WindPoint"`\n\x06\x44\x65vice\x12\x11\n\x04type\x18\x01 \x01(\rH\x00\x88\x01\x01\x12\x15\n\rserial_number\x18\x02 \x01(\r\x12#\n\rdevice_points\x18\x03 \x03(\x0b\x32\x0c.DevicePointB\x07\n\x05_type"\xa2\x08\n\x0b\x44\x65vicePoint\x12\x16\n\ttimestamp\x18\x01 \x01(\rH\x00\x88\x01\x01\x12\x1a\n\rdevice_status\x18\x02 \x01(\rH\x01\x88\x01\x01\x12\x0c\n\x04ldsa\x18\x03 \x01(\r\x12!\n\x19\x61verage_particle_diameter\x18\x04 \x01(\r\x12%\n\x1dparticle_number_concentration\x18\x05 \x01(\r\x12\x13\n\x0btemperature\x18\x06 \x01(\x05\x12\x19\n\x11relative_humidity\x18\x07 \x01(\r\x12\x17\n\x0f\x62\x61ttery_voltage\x18\x08 \x01(\r\x12\x15\n\rparticle_mass\x18\t \x01(\r\x12\x16\n\x0e\x63orona_voltage\x18\n \x01(\r\x12\x19\n\x11\x64iffusion_current\x18\x0b \x01(\r\x12\x1a\n\x12\x64\x65position_voltage\x18\x0c \x01(\r\x12\x0c\n\x04\x66low\x18\r \x01(\r\x12\x18\n\x10\x61mbient_pressure\x18\x0e \x01(\r\x12\x1b\n\x13\x65lectrometer_offset\x18\x0f \x01(\r\x12\x1d\n\x15\x65lectrometer_2_offset\x18\x10 \x01(\r\x12\x19\n\x11\x65lectrometer_gain\x18\x11 \x01(\r\x12\x1b\n\x13\x65lectrometer_2_gain\x18\x12 \x01(\r\x12 \n\x18\x64iffusion_current_offset\x18\x13 \x01(\r\x12\x1c\n\x14particle_number_10nm\x18\x14 \x01(\r\x12\x1c\n\x14particle_number_16nm\x18\x15 \x01(\r\x12\x1c\n\x14particle_number_26nm\x18\x16 \x01(\r\x12\x1c\n\x14particle_number_43nm\x18\x17 \x01(\r\x12\x1c\n\x14particle_number_70nm\x18\x18 \x01(\r\x12\x1d\n\x15particle_number_114nm\x18\x19 \x01(\r\x12\x1d\n\x15particle_number_185nm\x18\x1a \x01(\r\x12\x1d\n\x15particle_number_300nm\x18\x1b \x01(\r\x12\x0f\n\x07surface\x18\x1c \x01(\r\x12\x17\n\x0fsigma_size_dist\x18\x1d \x01(\r\x12\x17\n\x0fsteps_inversion\x18\x1e \x01(\r\x12\x16\n\x0e\x63urrent_dist_0\x18\x1f \x01(\r\x12\x16\n\x0e\x63urrent_dist_1\x18  \x01(\r\x12\x16\n\x0e\x63urrent_dist_2\x18! \x01(\r\x12\x16\n\x0e\x63urrent_dist_3\x18" \x01(\r\x12\x16\n\x0e\x63urrent_dist_4\x18# \x01(\r\x12\x14\n\x0cpump_current\x18$ \x01(\r\x12\x10\n\x08pump_pwm\x18% \x01(\r\x12\x16\n\tcs_status\x18& \x01(\x05H\x02\x88\x01\x01\x42\x0c\n\n_timestampB\x10\n\x0e_device_statusB\x0c\n\n_cs_status"\xb4\x02\n\x0cGatewayPoint\x12\x16\n\ttimestamp\x18\x01 \x01(\rH\x00\x88\x01\x01\x12\x15\n\rserial_number\x18\x02 \x01(\r\x12\x18\n\x10\x66irmware_version\x18\x03 \x01(\r\x12\x13\n\x0b\x66ree_memory\x18\x04 \x01(\r\x12\x11\n\tfree_heap\x18\x05 \x01(\r\x12\x1f\n\x17largest_free_block_heap\x18\x06 \x01(\r\x12\x17\n\x0f\x63\x65llular_signal\x18\x07 \x01(\x05\x12\x17\n\x0f\x62\x61ttery_int_soc\x18\x08 \x01(\r\x12\x17\n\x0f\x62\x61ttery_ext_soc\x18\t \x01(\r\x12\x1b\n\x13\x62\x61ttery_ext_voltage\x18\n \x01(\r\x12\x1c\n\x14\x63harging_ext_voltage\x18\x0b \x01(\rB\x0c\n\n_timestamp"Z\n\rPositionPoint\x12\x16\n\ttimestamp\x18\x01 \x01(\rH\x00\x88\x01\x01\x12\x10\n\x08latitude\x18\x02 \x01(\x02\x12\x11\n\tlongitude\x18\x03 \x01(\x02\x42\x0c\n\n_timestamp"\x81\x01\n\tWindPoint\x12\x16\n\ttimestamp\x18\x01 \x01(\rH\x00\x88\x01\x01\x12\x17\n\nwind_speed\x18\x02 \x01(\rH\x01\x88\x01\x01\x12\x17\n\nwind_angle\x18\x03 \x01(\rH\x02\x88\x01\x01\x42\x0c\n\n_timestampB\r\n\x0b_wind_speedB\r\n\x0b_wind_angleb\x06proto3'
)

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "protoV1_pb2", _globals)
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    _globals["_COMBINEDDATA"]._serialized_start = 18
    _globals["_COMBINEDDATA"]._serialized_end = 194
    _globals["_DEVICE"]._serialized_start = 196
    _globals["_DEVICE"]._serialized_end = 292
    _globals["_DEVICEPOINT"]._serialized_start = 295
    _globals["_DEVICEPOINT"]._serialized_end = 1353
    _globals["_GATEWAYPOINT"]._serialized_start = 1356
    _globals["_GATEWAYPOINT"]._serialized_end = 1664
    _globals["_POSITIONPOINT"]._serialized_start = 1666
    _globals["_POSITIONPOINT"]._serialized_end = 1756
    _globals["_WINDPOINT"]._serialized_start = 1759
    _globals["_WINDPOINT"]._serialized_end = 1888
# @@protoc_insertion_point(module_scope)

"""Hardware-free tests for the BLE payload decoders.

The expected values were recorded from the previous per-field decoders for
fixed payloads, so these tests pin the byte layout, not just the code.
"""

import pytest

from naneos.ble.partector.characteristics import (
    PartectorBleDecoderAux,
    PartectorBleDecoderAuxError,
    PartectorBleDecoderSize,
    PartectorBleDecoderStd,
)
from naneos.data_point import NaneosDeviceDataPoint

RECORDED = {
    PartectorBleDecoderStd: (
        "e13b032e112a32b579080f08b1f7ed4c2e5d3a07",
        {
            "serial_number": 19693,
            "device_status": 198671,
            "ldsa": 2119.37,
            "particle_number_concentration": 11874858.0,
            "average_particle_diameter": 4398.0,
            "particle_mass": 38249.42,
            "temperature": 121.0,
            "relative_humidity": 8.0,
            "battery_voltage": 634.09,
        },
    ),
    PartectorBleDecoderAux: (
        "f97f21ee232d178a209af6b5887f66e8092402aa",
        {
            "diffusion_current": 609.61,
            "diffusion_current_offset": 43522.0,
            "corona_voltage": 32761.0,
            "electrometer_1_amplitude": 46582.0,
            "electrometer_2_amplitude": 32648.0,
            "electrometer_1_gain": 59494.0,
            "electrometer_2_gain": 9225.0,
            "deposition_voltage": 11555.0,
            "flow_from_dp": 35.351,
            "ambient_pressure": 39456.0,
        },
    ),
    PartectorBleDecoderAuxError: (
        "ffffc1551b27fe53266e490db138489ce814d58d",
        {
            "device_status": 656102849,
            "diffusion_current_average": 281.98,
            "diffusion_current_stddev": 34.01,
            "diffusion_current_max": 145.13,
            "diffusion_current_delay_on": 254,
            "diffusion_current_delay_off": 83,
            "corona_voltage_onset": 40008,
        },
    ),
    PartectorBleDecoderSize: (
        "145a8b4f994fed15c5b2fdaeeff317f157e1e097",
        {
            "particle_number_10nm": 743956.0,
            "particle_number_16nm": 627960.0,
            "particle_number_26nm": 388431.0,
            "particle_number_43nm": 732241.0,
            "particle_number_70nm": 1027837.0,
            "particle_number_114nm": 98110.0,
            "particle_number_185nm": 88049.0,
            "particle_number_300nm": 622094.0,
        },
    ),
}


@pytest.mark.parametrize("decoder", list(RECORDED), ids=lambda d: d.__name__)
def test_decoder_reproduces_recorded_values_exactly(decoder) -> None:
    payload_hex, expected = RECORDED[decoder]

    decoded = decoder.decode(bytes.fromhex(payload_hex)).to_dict()

    assert decoded == expected
    for name, value in expected.items():
        assert type(decoded[name]) is type(value), name


@pytest.mark.parametrize("decoder", list(RECORDED), ids=lambda d: d.__name__)
def test_field_names_match_what_decode_sets(decoder) -> None:
    payload_hex, expected = RECORDED[decoder]

    assert decoder.FIELD_NAMES == set(expected)


def test_decoding_into_an_existing_point_keeps_its_other_fields() -> None:
    point = NaneosDeviceDataPoint(serial_number=8617, ldsa=1.5)
    payload_hex, expected = RECORDED[PartectorBleDecoderAux]

    result = PartectorBleDecoderAux.decode(bytes.fromhex(payload_hex), data_structure=point)

    assert result is point
    assert point.serial_number == 8617
    assert point.ldsa == 1.5
    assert point.corona_voltage == expected["corona_voltage"]


def test_error_frame_marker() -> None:
    assert PartectorBleDecoderAuxError.is_error_frame(b"\xff\xff" + bytes(18))
    assert not PartectorBleDecoderAuxError.is_error_frame(b"\xff\x00" + bytes(18))
    assert not PartectorBleDecoderAuxError.is_error_frame(b"\xff")


def test_std_serial_number_helper_matches_decode() -> None:
    payload = bytes.fromhex(RECORDED[PartectorBleDecoderStd][0])
    assert PartectorBleDecoderStd.get_serial_number(payload) == 19693

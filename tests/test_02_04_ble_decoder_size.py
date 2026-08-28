from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint
from naneos.partector_ble.decoder.partector_ble_decoder_size import PartectorBleDecoderSize

# The size_dist characteristic packs 8 channels as 20-bit little-endian values into 20 bytes.
CHANNELS = ["10", "16", "26", "43", "70", "114", "185", "300"]


def _pack(values: list[int]) -> bytes:
    """Pack 8 channel values as consecutive 20-bit little-endian fields."""
    bits = 0
    for i, value in enumerate(values):
        bits |= (value & 0xFFFFF) << (20 * i)
    return bits.to_bytes(20, "little")


def test_size_decoder_maps_every_channel_to_its_own_field() -> None:
    """Each channel must decode its own slice, not another channel's."""
    values = [11, 22, 33, 44, 55, 66, 77, 88]
    decoded = PartectorBleDecoderSize.decode(_pack(values))

    for channel, expected in zip(CHANNELS, values):
        assert getattr(decoded, f"particle_number_{channel}nm") == float(expected)


def test_size_decoder_handles_full_range() -> None:
    """A 20-bit field must decode its maximum value without bleeding into its neighbour."""
    values = [0xFFFFF, 0, 0xFFFFF, 0, 0xFFFFF, 0, 0xFFFFF, 0]
    decoded = PartectorBleDecoderSize.decode(_pack(values))

    for channel, expected in zip(CHANNELS, values):
        assert getattr(decoded, f"particle_number_{channel}nm") == float(expected)


def test_size_decoder_fills_given_data_structure() -> None:
    """Decoding into an existing data point must not disturb its other fields."""
    values = [1, 2, 3, 4, 5, 6, 7, 8]
    data_point = NaneosDeviceDataPoint(serial_number=8617)

    decoded = PartectorBleDecoderSize.decode(_pack(values), data_structure=data_point)

    assert decoded is data_point
    assert decoded.serial_number == 8617
    for channel, expected in zip(CHANNELS, values):
        assert getattr(decoded, f"particle_number_{channel}nm") == float(expected)

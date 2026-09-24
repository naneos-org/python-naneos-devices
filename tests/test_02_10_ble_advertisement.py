"""Hardware-free tests for picking the Partector frame out of a BLE advertisement."""

from types import SimpleNamespace

from naneos.ble.partector.advertisement import PartectorBleDecoder


def _frame(kind: bytes, fill: int) -> bytes:
    """protocol byte, 20 payload bytes, protocol byte"""
    return kind + bytes([fill]) * 20 + b"F"


def _adv(*frames: bytes) -> SimpleNamespace:
    """The frames as a backend delivers them: the first two bytes are the manufacturer id."""
    return SimpleNamespace(
        manufacturer_data={int.from_bytes(f[:2], "little"): f[2:] for f in frames}
    )


def test_the_payload_of_the_advertisement_frame_is_returned() -> None:
    payload = PartectorBleDecoder.decode_partector_advertisement(_adv(_frame(b"X", 7)))  # type: ignore[arg-type]
    assert payload == bytes([7]) * 20


def test_the_newest_advertisement_wins_over_the_stale_ones_bluez_keeps() -> None:
    adv = _adv(_frame(b"X", 1), _frame(b"Y", 9), _frame(b"X", 2))
    assert PartectorBleDecoder.decode_partector_advertisement(adv) == bytes([2]) * 20  # type: ignore[arg-type]


def test_a_backend_that_joins_advertisement_and_scan_response_is_split() -> None:
    joined = _frame(b"X", 3) + _frame(b"Y", 4)
    adv = SimpleNamespace(manufacturer_data={int.from_bytes(joined[:2], "little"): joined[2:]})
    assert PartectorBleDecoder.decode_partector_advertisement(adv) == bytes([3]) * 20  # type: ignore[arg-type]


def test_a_scan_response_alone_or_a_damaged_frame_is_not_an_advertisement() -> None:
    decode = PartectorBleDecoder.decode_partector_advertisement
    assert decode(_adv(_frame(b"Y", 4))) is None  # type: ignore[arg-type]
    assert decode(_adv(_frame(b"X", 5)[:-1] + b"Z")) is None  # type: ignore[arg-type]
    assert decode(_adv(_frame(b"X", 5)[:-2])) is None  # type: ignore[arg-type]
    assert decode(_adv()) is None  # type: ignore[arg-type]

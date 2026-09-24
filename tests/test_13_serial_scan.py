"""Hardware-free tests for the identification of a device behind a serial port."""

import pytest
from fake_transport import FakeTransport

from naneos.data_point import DeviceType
from naneos.usb.partector import scan


def _scan(monkeypatch, transport: FakeTransport) -> scan.FoundDevice | None:
    monkeypatch.setattr(scan, "SerialTransport", lambda port: transport)
    monkeypatch.setattr(scan, "_ANSWER_TIMEOUT_SECONDS", 0.03)
    return scan._scan_port("/dev/fake")


def test_scan_identifies_each_family(monkeypatch) -> None:
    pro = _scan(monkeypatch, FakeTransport(8764, 424, "P2pro"))
    assert pro == scan.FoundDevice(8764, "/dev/fake", DeviceType.P2PRO, 424)

    assert _scan(monkeypatch, FakeTransport(8617, 422, "P2")).kind == DeviceType.P2  # type: ignore[union-attr]
    # older firmware has no name query, low serial numbers are the P1 family
    assert _scan(monkeypatch, FakeTransport(8000, 298, "P2pro")).kind == DeviceType.P2  # type: ignore[union-attr]
    assert _scan(monkeypatch, FakeTransport(24, 100)).kind == DeviceType.P1  # type: ignore[union-attr]


def test_scan_ignores_a_port_without_a_partector_and_closes_it(monkeypatch) -> None:
    transport = FakeTransport()
    transport.mute = True

    assert _scan(monkeypatch, transport) is None
    assert not transport.is_open


def test_a_garbled_name_is_asked_again(monkeypatch) -> None:
    transport = FakeTransport(8764, 424, "P2pro")
    write = transport.write
    garbled = ["0.75"]  # the tail of a verbose line that was cut off

    def flaky_write(command: str) -> None:
        if command == "name?" and garbled:
            transport._lines.put(garbled.pop())
            return
        write(command)

    transport.write = flaky_write  # type: ignore[method-assign]

    assert _scan(monkeypatch, transport).kind == DeviceType.P2PRO  # type: ignore[union-attr]


@pytest.mark.parametrize("stalled", ["f?", "name?"])
def test_a_pro_that_answers_one_question_late_is_still_a_pro(monkeypatch, stalled: str) -> None:
    """A P2 Pro pauses once per size distribution cycle. The answer to the
    question that hit the pause then arrives together with the answer to the
    next one, and must not be taken for it."""
    transport = FakeTransport(8764, 424, "P2pro")
    write = transport.write
    late: list[str] = []

    def stalling_write(command: str) -> None:
        if late:
            transport._lines.put(transport.answers[late.pop()])
        if command == stalled and stalled not in transport.written:
            transport.written.append(command)
            late.append(command)  # answered on the next write only
            return
        write(command)

    transport.write = stalling_write  # type: ignore[method-assign]

    assert _scan(monkeypatch, transport) == scan.FoundDevice(
        8764, "/dev/fake", DeviceType.P2PRO, 424
    )


def test_the_name_a_device_gives_tells_its_type_the_same_way_on_usb_and_ble() -> None:
    assert DeviceType.from_name("P2") is DeviceType.P2  # 0: must not be mistaken for "unknown"
    assert DeviceType.from_name("P2pro") is DeviceType.P2PRO
    assert DeviceType.from_name("") is None
    assert DeviceType.from_name("P2 Pro") is None  # a cut off or unknown answer is not guessed


def test_an_unknown_firmware_still_asks_for_the_name(monkeypatch) -> None:
    transport = FakeTransport(8764, 424, "P2pro")
    del transport.answers["f?"]

    found = _scan(monkeypatch, transport)
    assert found == scan.FoundDevice(8764, "/dev/fake", DeviceType.P2PRO, None)

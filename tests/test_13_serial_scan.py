"""Hardware-free tests for the identification of a device behind a serial port."""

from fake_transport import FakeTransport

from naneos.data_point import DeviceType
from naneos.usb import scan


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

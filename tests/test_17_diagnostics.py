"""Hardware-free tests for the UI curve and pulse form readouts, their upload and
the manager's schedule."""

import asyncio
import queue
import time
from types import SimpleNamespace

import pytest
from bleak.backends.device import BLEDevice
from fake_response import FakeResponse, wrapped
from fake_transport import FakeTransport

from naneos import manager as manager_module
from naneos.ble.partector import readout as readout_module
from naneos.ble.partector.characteristics import PartectorBleDiagnosticsPackets
from naneos.ble.partector.connection import PartectorBleConnection
from naneos.cli import parse_args
from naneos.cloud import upload as upload_module
from naneos.cloud.upload import backend_status, upload_pulse_form, upload_ui_curve
from naneos.data_point import ConnectionType, DeviceType
from naneos.device import NotSupportedError
from naneos.diagnostics import PulseForm, UiCurve
from naneos.manager import NaneosDeviceManager
from naneos.protobuf import proto_v2_pb2 as pb
from naneos.protobuf.protobuf import create_pulse_form, create_ui_curve
from naneos.usb.partector.device import Partector1, Partector2

# What a P2 (SN8617, FW422) answered on 2026-09-21, shortened: 100 lines of
# "voltage<TAB>current" for "UI?", one line of 200 values with a trailing tab
# for "pulse?".
UI_LINES = [f"{5000 - 50 * i}\t{max(0, 198 - 2 * i)}" for i in range(100)]  # not sorted
PULSE_LINE = "\t".join(str(v) for v in range(200)) + "\t"


def _p2(**kwargs) -> tuple[Partector2, FakeTransport]:
    transport = FakeTransport(firmware=kwargs.pop("firmware", 422))
    transport.answers["UI?"] = UI_LINES
    transport.answers["pulse?"] = PULSE_LINE
    kwargs.setdefault("gain_test_active", False)
    kwargs.setdefault("output_pulse_diagnostics", False)
    return Partector2(transport=transport, **kwargs), transport  # type: ignore[arg-type]


@pytest.fixture
def no_sweep_wait(monkeypatch):
    """The device gets 10 s to compute the curve; the fake needs none."""
    monkeypatch.setattr("naneos.usb.partector.device.UI_COMPUTE_SECONDS", 0)


# == USB ===========================================================================================
def test_usb_ui_curve_is_read_sorted_by_voltage_and_the_data_is_held_back(no_sweep_wait) -> None:
    device, transport = _p2()
    try:
        transport.emit(18)
        curve = device.read_ui_curve()

        assert transport.written[-2:] == ["UI!", "UI?"]
        assert isinstance(curve, UiCurve)
        assert curve.is_complete
        assert curve.device_type == DeviceType.P2
        assert curve.serial_number == 8617
        assert abs(curve.unix_timestamp - time.time()) < 5
        assert curve.voltages == tuple(50 * i + 50 for i in range(100))
        assert curve.currents[-1] == 1.98  # nA
        assert curve.currents[0] == 0.0

        # The sweep disturbs the measurement: lines during it are dropped.
        transport.emit(18)
        time.sleep(0.1)
        assert device.get_data() == []
        assert not device.is_settling  # the gain test flag is not touched
        device._sweep_until = 0
        transport.emit(18)
        time.sleep(0.1)
        assert len(device.get_data()) == 1
    finally:
        device.close()


def test_usb_pulse_form_takes_the_line_with_or_without_the_trailing_tab() -> None:
    device, transport = _p2()
    try:
        form = device.read_pulse_form()
        assert isinstance(form, PulseForm)
        assert form.is_complete
        assert form.currents[:3] == (0.0, 0.01, 0.02)
        assert form.currents[-1] == 1.99
        assert transport.written[-1] == "pulse?"

        transport.answers["pulse?"] = PULSE_LINE.rstrip("\t")
        assert device.read_pulse_form().is_complete
    finally:
        device.close()


def test_usb_readout_times_out_with_an_incomplete_answer_and_recovers(no_sweep_wait) -> None:
    device, transport = _p2()
    try:
        transport.answers["UI?"] = UI_LINES[:99]
        with pytest.raises(TimeoutError, match="99 of 100"):
            device.read_ui_curve(timeout=0.3)

        assert device._capture is None
        transport.answers["UI?"] = UI_LINES
        assert device.read_ui_curve().is_complete
        assert device.query("f?") == ["422"]  # commands work as before
    finally:
        device.close()


def test_usb_readout_needs_firmware_418_and_a_partector_2() -> None:
    device, _ = _p2(firmware=417)
    try:
        with pytest.raises(NotSupportedError, match="418"):
            device.read_ui_curve()
        with pytest.raises(NotSupportedError, match="418"):
            device.read_pulse_form()
    finally:
        device.close()

    p1 = Partector1(transport=FakeTransport(serial_number=1234, firmware=500))  # type: ignore[arg-type]
    try:
        with pytest.raises(NotSupportedError):
            p1.read_pulse_form()
    finally:
        p1.close()


def test_usb_measurement_lines_and_replies_pass_through_during_a_readout(no_sweep_wait) -> None:
    device, transport = _p2()
    try:
        # A verbose line and a one-field reply arrive between the curve points.
        transport.answers["UI?"] = [*UI_LINES[:50], "\t".join(["1"] * 18), "42", *UI_LINES[50:]]
        curve = device.read_ui_curve()
        assert curve.is_complete
        time.sleep(0.1)
        assert len(device.get_data()) == 0  # held back by the sweep, not eaten by the capture
        assert device._replies.get_nowait() == ["42"]
    finally:
        device.close()


# == BLE ===========================================================================================
def _ui_packet(points: list[tuple[int, int]], last: bool) -> bytes:
    data = bytes([254 if last else 255, 254])
    for voltage, current in points:
        data += voltage.to_bytes(2, "little") + bytes([current])
    return data.ljust(20, b"\0")


def _pulse_packet(
    first_index: int, values: list[int], last: bool, reserved: tuple[int, int] = (0, 0)
) -> bytes:
    """8 (index, value) pairs from byte 2, then the 2 reserved bytes 18 and 19."""
    assert len(values) == 8
    data = bytes([254 if last else 255, 253])
    for i, value in enumerate(values):
        data += bytes([first_index + i, value])
    return data + bytes(reserved)


def _pulse_packets(values: list[int]) -> list[bytes]:
    """The 25 packets of a pulse form. Like the firmware (seen on SN8617 and SN8764) they carry
    the first pair of the next packet in the reserved bytes; the last one carries index 200."""
    assert len(values) == 200
    following = [*values, 0]
    return [
        _pulse_packet(i, values[i : i + 8], last=i == 192, reserved=(i + 8, following[i + 8]))
        for i in range(0, 200, 8)
    ]


def test_ble_packets_are_told_apart_and_decoded() -> None:
    ui = _ui_packet([(498, 0), (3735, 198), (0, 0), (0, 0), (0, 0)], last=False)
    pulse = _pulse_packet(8, [0, 6, 72, 206, 0, 0, 0, 1], last=True, reserved=(16, 99))
    aux = bytes(20)
    aux_error = b"\xff\xff" + bytes(18)

    assert PartectorBleDiagnosticsPackets.is_ui_curve(ui)
    assert not PartectorBleDiagnosticsPackets.is_last(ui)
    assert PartectorBleDiagnosticsPackets.is_pulse_form(pulse)
    assert PartectorBleDiagnosticsPackets.is_last(pulse)
    assert not PartectorBleDiagnosticsPackets.is_diagnostics(aux)
    assert not PartectorBleDiagnosticsPackets.is_diagnostics(aux_error)

    assert PartectorBleDiagnosticsPackets.ui_curve_points(ui)[:2] == [(498, 0.0), (3735, 1.98)]
    assert PartectorBleDiagnosticsPackets.pulse_form_values(pulse)[:4] == [
        (8, 0.0),
        (9, 0.06),
        (10, 0.72),
        (11, 2.06),
    ]
    # 8 pairs: the reserved bytes 18 and 19 (16, 99) are not a ninth one
    assert len(PartectorBleDiagnosticsPackets.pulse_form_values(pulse)) == 8
    assert PartectorBleDiagnosticsPackets.pulse_form_values(pulse)[-1] == (15, 0.01)


class _FakeClient:
    def __init__(self) -> None:
        self.is_connected = False
        self.services = SimpleNamespace(
            get_service=lambda u: object(), get_characteristic=lambda u: object()
        )
        self.calls: list[str] = []
        self.callbacks: dict = {}
        self.aux_frames: list[bytes] = []  # sent on "aux" after every write

    async def connect(self, timeout=None):
        self.is_connected = True

    async def start_notify(self, uuid, callback):
        self.callbacks[uuid] = callback

    async def write_gatt_char(self, uuid, data, response=False):
        self.calls.append(f"write:{bytes(data).decode()}")
        for frame in self.aux_frames:
            self.callbacks[PartectorBleConnection.CHAR_UUIDS["aux"]](None, bytearray(frame))

    async def stop_notify(self, uuid):
        pass

    async def disconnect(self):
        self.is_connected = False


@pytest.fixture
def connection(monkeypatch) -> PartectorBleConnection:
    monkeypatch.setattr(PartectorBleConnection, "_new_client", lambda self: _FakeClient())
    # The device gets 10 s to compute the curve; the fake needs none.
    monkeypatch.setattr(readout_module, "UI_COMPUTE_SECONDS", 0)
    loop = asyncio.new_event_loop()
    device = BLEDevice("AA:BB:CC:DD:EE:FF", "P2", None)
    conn = PartectorBleConnection(
        device, loop, 8617, PartectorBleConnection.create_connection_queue()
    )
    conn._firmware_version = 422
    yield conn
    loop.close()


def test_ble_ui_curve_is_assembled_from_the_packets_and_the_data_held_back(connection) -> None:
    async def scenario() -> None:
        connection._loop = asyncio.get_running_loop()
        await connection._try_connect()
        points = [(5000 - 50 * i, max(0, 198 - 2 * i)) for i in range(100)]
        packets = [_ui_packet(points[i : i + 5], last=i == 95) for i in range(0, 100, 5)]
        connection._client.aux_frames = [bytes(20), *packets]  # a measurement frame first

        curve = await connection.read_ui_curve()

        assert connection._client.calls[-2:] == ["write:UI!", "write:UI?"]
        assert curve.is_complete
        assert curve.voltages[:3] == (50, 100, 150)
        assert curve.currents[-1] == 1.98
        assert curve.serial_number == 8617

        connection._emit_data_point()
        assert connection._queue.empty()  # held back during the sweep
        connection._readout.hold_points_until = 0
        connection._emit_data_point()
        assert connection._queue.get_nowait().serial_number == 8617

    asyncio.run(scenario())


def test_ble_ui_curve_with_a_lost_or_a_stray_packet_is_left_incomplete(connection) -> None:
    async def scenario() -> None:
        connection._loop = asyncio.get_running_loop()
        await connection._try_connect()
        points = [(5000 - 50 * i, max(0, 198 - 2 * i)) for i in range(100)]
        packets = [_ui_packet(points[i : i + 5], last=i == 95) for i in range(0, 100, 5)]

        connection._client.aux_frames = [*packets[:7], *packets[8:]]  # one packet lost
        curve = await connection.read_ui_curve()
        assert not curve.is_complete
        assert curve.entries == "95 U + 95 I values"

        connection._client.aux_frames = [*packets[:-1], packets[0], packets[-1]]  # one too many
        curve = await connection.read_ui_curve()
        assert not curve.is_complete  # not cut to 100 any more
        assert curve.entries == "105 U + 105 I values"

    asyncio.run(scenario())


def test_ble_pulse_form_with_a_lost_packet_is_left_short(connection) -> None:
    async def scenario() -> None:
        connection._loop = asyncio.get_running_loop()
        await connection._try_connect()
        packets = _pulse_packets(list(range(200)))

        # The packet of the samples 80 to 87 is lost. Its first sample sits in the reserved
        # bytes of the packet before, which are not read: all 8 are missing.
        connection._client.aux_frames = [*packets[:10], *packets[11:]]
        form = await connection.read_pulse_form()
        assert not form.is_complete
        assert form.entries == "192 I values"

    asyncio.run(scenario())


def test_ble_pulse_form_does_not_read_the_reserved_bytes(connection) -> None:
    async def scenario() -> None:
        connection._loop = asyncio.get_running_loop()
        await connection._try_connect()
        values = list(range(200))
        # A pair at index 0 in the reserved bytes would overwrite the first sample if it was read.
        packets = [
            _pulse_packet(i, values[i : i + 8], last=i == 192, reserved=(0, 99))
            for i in range(0, 200, 8)
        ]
        connection._client.aux_frames = packets

        form = await connection.read_pulse_form()
        assert form.is_complete
        assert form.currents == tuple(v / 100 for v in values)

    asyncio.run(scenario())


def test_ble_data_is_not_held_back_when_the_sweep_could_not_be_started(
    connection, monkeypatch
) -> None:
    async def refuse(command: str) -> None:
        raise ConnectionError("not connected")

    monkeypatch.setattr(connection, "write", refuse)

    async def scenario() -> None:
        with pytest.raises(ConnectionError):
            await connection.read_ui_curve()

    asyncio.run(scenario())
    assert connection._readout.hold_points_until == 0.0


def test_ble_pulse_form_is_assembled_and_a_stray_packet_is_ignored(connection) -> None:
    async def scenario() -> None:
        connection._loop = asyncio.get_running_loop()
        await connection._try_connect()
        packets = _pulse_packets(list(range(200)))
        stray = _ui_packet([(1, 1)] * 5, last=True)  # from an earlier readout
        connection._client.aux_frames = [stray, *packets]

        form = await connection.read_pulse_form()
        assert form.is_complete
        assert form.currents[:3] == (0.0, 0.01, 0.02)
        assert form.currents[-1] == 1.99

        # Without a readout in flight the packets are dropped, never decoded as a measurement.
        aux = connection._client.callbacks[PartectorBleConnection.CHAR_UUIDS["aux"]]
        aux(None, bytearray(packets[0]))
        assert connection._decode_queue.empty()

        connection._client.aux_frames = packets[:-1]
        with pytest.raises(TimeoutError, match="24 packets"):
            await connection.read_pulse_form(timeout=0.05)

    asyncio.run(scenario())


def test_ble_readout_needs_the_firmware_version(connection) -> None:
    async def scenario() -> None:
        connection._firmware_version = None
        with pytest.raises(NotSupportedError):
            await connection.read_pulse_form()
        connection._firmware_version = 400
        with pytest.raises(NotSupportedError, match="418"):
            await connection.read_ui_curve()

    asyncio.run(scenario())


# == Protobuf and upload ===========================================================================
CURVE = UiCurve(DeviceType.P2PRO, 8764, 1_700_000_000, (0, 498, 3735), (0.0, 0.5, 1.98))
FORM = PulseForm(DeviceType.P2, 8617, 1_700_000_001, (0.0, 0.06, 2.06))


def test_diagnostics_go_on_the_wire_at_the_scale_of_the_schema() -> None:
    curve = pb.UiCurve.FromString(create_ui_curve(CURVE).SerializeToString())
    assert curve.type == DeviceType.P2PRO
    assert curve.serial_number == 8764
    assert curve.abs_timestamp == 1_700_000_000
    assert list(curve.U_values) == [0, 498, 3735]
    assert list(curve.I_values) == [0, 50, 198]

    form = pb.PulseForm.FromString(create_pulse_form(FORM).SerializeToString())
    assert form.type == DeviceType.P2
    assert list(form.I_values) == [0, 6, 206]  # nA * 100


def test_diagnostics_are_posted_to_their_own_endpoints(monkeypatch) -> None:
    posts = []
    monkeypatch.setattr(
        upload_module.requests,
        "post",
        lambda url, headers, data, timeout: posts.append((url, data)) or FakeResponse(200),
    )
    upload_ui_curve(CURVE)
    upload_pulse_form(FORM)
    assert [url.rsplit("/", 1)[1] for url, _ in posts] == ["uicurve", "pulseform"]
    assert '"gateway": "python_webhook"' in posts[0][1]


def test_backend_status_sees_through_a_wrapped_answer() -> None:
    assert backend_status(FakeResponse(200, "not json")) == (200, "")
    assert backend_status(FakeResponse(200, '{"message": "no status here"}')) == (200, "")
    assert backend_status(FakeResponse(503, "busy")) == (503, "")
    assert backend_status(wrapped(200, "Wrote 100 data point(s)"))[0] == 200
    status, detail = backend_status(wrapped(404, "No data points found in your request"))
    assert status == 404
    assert "No data points found" in detail


# == Manager =======================================================================================
class _FakeDevice:
    """A device whose readouts follow a script: one entry per attempt, an int is the number
    of entries the result has (100 / 200 are complete), an exception is raised. What is
    left after the script is complete."""

    connection_type = ConnectionType.CONNECTED

    def __init__(
        self,
        serial_number: int,
        fails: bool = False,
        supported: bool = True,
        ui_script: list[int | Exception] | None = None,
        pulse_script: list[int | Exception] | None = None,
    ) -> None:
        self.serial_number = serial_number
        self.supported = supported
        self.ui_script = [TimeoutError("nothing")] * 10 if fails else list(ui_script or [])
        self.pulse_script = list(pulse_script or [])
        self.calls: list[str] = []
        self.on_call = lambda: None

    def read_ui_curve(self, timeout=None) -> UiCurve:
        self.calls.append("ui")
        self.on_call()
        if not self.supported:
            raise NotSupportedError("too old")
        count = self._next(self.ui_script, 100)
        values = tuple(range(count))
        return UiCurve(DeviceType.P2, self.serial_number, 1, values, tuple(map(float, values)))

    def read_pulse_form(self, timeout=None) -> PulseForm:
        self.calls.append("pulse")
        self.on_call()
        count = self._next(self.pulse_script, 200)
        return PulseForm(DeviceType.P2, self.serial_number, 1, tuple(map(float, range(count))))

    @staticmethod
    def _next(script: list[int | Exception], complete: int) -> int:
        step = script.pop(0) if script else complete
        if isinstance(step, Exception):
            raise step
        return step


def _wait_for(condition, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_manager_reads_every_device_in_turn_and_hands_the_results_on(monkeypatch) -> None:
    uploads = []
    monkeypatch.setattr(
        manager_module,
        "upload_diagnostic",
        lambda item: uploads.append(item) or FakeResponse(200),
    )
    manager = NaneosDeviceManager(use_serial=False, use_ble=False, upload_active=True)
    devices = [_FakeDevice(1), _FakeDevice(2, fails=True), _FakeDevice(3, supported=False)]
    monkeypatch.setattr(manager, "get_devices", lambda: devices)
    results: queue.Queue = queue.Queue()
    manager.register_diagnostics_queue(results)

    manager.request_diagnostics()
    manager._tick_diagnostics()
    assert _wait_for(lambda: not manager.diagnostics_in_progress)

    assert devices[0].calls == ["ui", "pulse"]
    # a curve that never comes is read three times, and does not stop the pulse form
    assert devices[1].calls == ["ui", "ui", "ui", "pulse"]
    assert devices[2].calls == ["ui"]  # not supported: the device is skipped
    got = [results.get_nowait() for _ in range(3)]
    assert [(type(d).__name__, d.serial_number) for d in got] == [
        ("UiCurve", 1),
        ("PulseForm", 1),
        ("PulseForm", 2),
    ]
    assert manager.pending_diagnostics_count == 3

    manager._drain_uploads()  # on the sender thread, after the snapshots
    assert uploads == got
    assert manager.pending_diagnostics_count == 0


def _diagnostics_manager(monkeypatch, *devices) -> tuple[NaneosDeviceManager, queue.Queue]:
    manager = NaneosDeviceManager(use_serial=False, use_ble=False, upload_active=True)
    monkeypatch.setattr(manager, "get_devices", lambda: list(devices))
    results: queue.Queue = queue.Queue()
    manager.register_diagnostics_queue(results)
    return manager, results


def _names(results: queue.Queue) -> list[str]:
    return [type(results.get_nowait()).__name__ for _ in range(results.qsize())]


def test_manager_reads_a_short_curve_again_and_only_the_complete_one_goes_on(
    monkeypatch, caplog
) -> None:
    device = _FakeDevice(1, ui_script=[95])
    manager, results = _diagnostics_manager(monkeypatch, device)

    with caplog.at_level("INFO", logger="naneos"):
        manager._read_all_diagnostics()

    assert device.calls == ["ui", "ui", "pulse"]
    got = [results.get_nowait() for _ in range(2)]
    assert [type(d).__name__ for d in got] == ["UiCurve", "PulseForm"]
    assert all(d.is_complete for d in got)
    assert results.empty()
    assert manager.pending_diagnostics_count == 2
    assert (
        "SN1 over BLE: UI curve attempt 1 of 3 incomplete: "
        "95 U + 95 I values, expected 100 U + 100 I values"
    ) in caplog.text
    assert "SN1 over BLE: read the UI curve, 100 U + 100 I values (attempt 2 of 3)" in caplog.text
    assert "SN1 over BLE: read the pulse form, 200 I values (attempt 1 of 3)" in caplog.text


def test_manager_drops_a_readout_that_is_still_wrong_after_three_attempts(
    monkeypatch, caplog
) -> None:
    device = _FakeDevice(1, ui_script=[95, 105, 99], pulse_script=[199, 0, 201])
    manager, results = _diagnostics_manager(monkeypatch, device)

    with caplog.at_level("INFO", logger="naneos"):
        manager._read_all_diagnostics()

    assert device.calls == ["ui", "ui", "ui", "pulse", "pulse", "pulse"]
    assert results.empty()
    assert manager.pending_diagnostics_count == 0
    assert "UI curve attempt 2 of 3 incomplete: 105 U + 105 I values, expected" in caplog.text
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert errors == [
        "SN1 over BLE: gave up on the UI curve after 3 attempts "
        "(99 U + 99 I values, expected 100 U + 100 I values), not uploaded.",
        "SN1 over BLE: gave up on the pulse form after 3 attempts "
        "(201 I values, expected 200 I values), not uploaded.",
    ]


@pytest.mark.parametrize(
    ("error", "retried"),
    [
        (TimeoutError("no last packet"), True),
        (ValueError("garbled line"), True),
        (ConnectionError("not connected"), False),
        (RuntimeError("wrong thread"), False),
    ],
)
def test_manager_reads_again_after_a_timeout_or_a_garbled_line_not_after_a_lost_link(
    monkeypatch, error, retried
) -> None:
    device = _FakeDevice(1, ui_script=[error])
    manager, results = _diagnostics_manager(monkeypatch, device)

    manager._read_all_diagnostics()

    assert device.calls == (["ui", "ui", "pulse"] if retried else ["ui", "pulse"])
    assert _names(results) == (["UiCurve", "PulseForm"] if retried else ["PulseForm"])


def test_manager_does_not_start_another_attempt_once_it_is_stopping(monkeypatch) -> None:
    device = _FakeDevice(1, ui_script=[95, 95, 95])
    manager, results = _diagnostics_manager(monkeypatch, device)
    device.on_call = manager._stop_event.set

    manager._read_all_diagnostics()

    assert device.calls == ["ui"]
    assert results.empty()


def test_the_counts_of_a_curve_and_a_form_are_told_and_checked() -> None:
    assert UiCurve.EXPECTED_ENTRIES == "100 U + 100 I values"
    assert PulseForm.EXPECTED_ENTRIES == "200 I values"
    assert CURVE.entries == "3 U + 3 I values"
    assert not CURVE.is_complete

    uneven = UiCurve(DeviceType.P2, 1, 1, (1,) * 100, (1.0,) * 99)
    assert uneven.entries == "100 U + 99 I values"
    assert not uneven.is_complete
    assert PulseForm(DeviceType.P2, 1, 1, (0.0,) * 200).is_complete
    assert not PulseForm(DeviceType.P2, 1, 1, (0.0,) * 201).is_complete

    assert NaneosDeviceManager._describe(CURVE) == "UiCurve of SN8764 (3 U + 3 I values)"
    assert NaneosDeviceManager._describe(FORM) == "PulseForm of SN8617 (3 I values)"


def test_manager_schedules_the_readouts_at_the_wall_clock_multiples(monkeypatch) -> None:
    manager = NaneosDeviceManager(use_serial=False, use_ble=False, diagnostics_interval_hours=1)
    started = []
    monkeypatch.setattr(manager, "_read_all_diagnostics", lambda: started.append(time.time()))

    now = 1_699_999_200 + 1800  # half past (1_699_999_200 is a full hour)
    monkeypatch.setattr(manager_module.time, "time", lambda: now)
    manager._tick_diagnostics()
    assert not started  # the first readout waits for the next full hour
    now += 1799
    manager._tick_diagnostics()
    assert not started
    now += 1
    manager._tick_diagnostics()
    assert _wait_for(lambda: len(started) == 1)
    manager._tick_diagnostics()
    assert len(started) == 1  # once per hour

    manager.diagnostics_interval_hours = None
    now += 3600
    manager._tick_diagnostics()
    assert len(started) == 1
    with pytest.raises(ValueError):
        manager.diagnostics_interval_hours = 0


@pytest.mark.parametrize("hours", [0.5, 1, 24])
def test_manager_takes_a_diagnostics_interval_from_half_an_hour_to_a_day(hours) -> None:
    manager = NaneosDeviceManager(use_serial=False, use_ble=False, diagnostics_interval_hours=hours)
    assert manager.diagnostics_interval_hours == hours


@pytest.mark.parametrize("hours", [0, -1, 0.49, 24.1, float("nan"), float("inf")])
def test_manager_refuses_a_diagnostics_interval_outside_half_an_hour_to_a_day(hours) -> None:
    with pytest.raises(ValueError, match="0.5 to 24 hours"):
        NaneosDeviceManager(use_serial=False, use_ble=False, diagnostics_interval_hours=hours)


def test_cli_diagnostics_interval_zero_means_never() -> None:
    assert parse_args([]).diagnostics_interval == 1.0
    assert parse_args(["--diagnostics-interval", "0"]).diagnostics_interval == 0
    assert parse_args(["--diagnostics-interval", "6"]).diagnostics_interval == 6.0


@pytest.mark.parametrize("value", ["0.5", "24"])
def test_cli_takes_the_ends_of_the_diagnostics_interval_range(value) -> None:
    assert parse_args(["--diagnostics-interval", value]).diagnostics_interval == float(value)


@pytest.mark.parametrize(
    "value", ["-1", "-0.5", "0.49", "0.1", "24.1", "100", "nan", "inf", "soon"]
)
def test_cli_rejects_a_diagnostics_interval_the_manager_would_refuse(value, capsys) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--diagnostics-interval", value])
    assert "--diagnostics-interval" in capsys.readouterr().err

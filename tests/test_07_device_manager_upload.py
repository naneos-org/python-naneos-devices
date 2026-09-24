"""Hardware-free tests for the upload backlog and sender of NaneosDeviceManager."""

import queue
import threading
import time
from types import SimpleNamespace

import pandas as pd
import pytest
import requests
from fake_response import FakeResponse, wrapped

from naneos import manager as module
from naneos.data_point import DeviceType
from naneos.diagnostics import PulseForm, UiCurve
from naneos.manager import NaneosDeviceManager


def _snapshot(serial: int, ts: int) -> dict[int, pd.DataFrame]:
    """One row at `ts` milliseconds, like the frames the manager gathers."""
    df = pd.DataFrame({"unix_timestamp": [ts], "ldsa": [1.0]}).set_index("unix_timestamp")
    return {serial: df}


def _seconds(call) -> list[int]:
    """The unix seconds of the rows one request carried."""
    return list(call[1].index)


def _manager(**kwargs) -> NaneosDeviceManager:
    return NaneosDeviceManager(use_serial=False, use_ble=False, upload_active=True, **kwargs)


@pytest.fixture
def uploads(monkeypatch):
    """Replace the network call; `outcomes` is consumed one entry per attempt."""
    state = SimpleNamespace(outcomes=[], calls=[])

    def fake_send(frames):
        state.calls.append(frames)
        outcome = state.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome if isinstance(outcome, FakeResponse) else FakeResponse(outcome)

    monkeypatch.setattr(module, "send_frames", fake_send)
    return state


def test_publishing_never_touches_the_network(uploads) -> None:
    manager = _manager()

    manager._publish_snapshot(_snapshot(1, 1000))

    assert uploads.calls == []
    assert manager.pending_upload_count == 1


def test_failed_snapshot_is_kept_and_sent_when_the_network_is_back(uploads) -> None:
    manager = _manager()

    uploads.outcomes = [ConnectionError("no network")]
    manager._publish_snapshot(_snapshot(1, 1000))
    assert manager._drain_uploads() is False
    assert manager.pending_upload_count == 1

    uploads.outcomes = [200, 200]
    manager._publish_snapshot(_snapshot(1, 2000))
    assert manager._drain_uploads() is True

    assert manager.pending_upload_count == 0
    assert [_seconds(c) for c in uploads.calls] == [[1], [1], [2]]  # oldest first


def test_what_gathered_during_an_outage_goes_out_in_one_request(uploads) -> None:
    manager = _manager()
    uploads.outcomes = [ConnectionError("no network")]
    manager._publish_snapshot(_snapshot(1, 1_000))
    manager._drain_uploads()

    for ts in (31_000, 61_000, 91_000):  # 30 s apart, no drain: the network is still down
        manager._publish_snapshot(_snapshot(1, ts))
    assert manager.pending_upload_count == 4

    uploads.outcomes = [200, 200]
    assert manager._drain_uploads() is True

    assert [_seconds(c) for c in uploads.calls] == [
        [1],
        [1],
        [31, 61, 91],
    ]  # 3 snapshots, 1 request


def test_server_errors_retry_but_client_errors_drop(uploads) -> None:
    manager = _manager()

    uploads.outcomes = [503]
    manager._publish_snapshot(_snapshot(1, 1000))
    assert manager._drain_uploads() is False
    assert manager.pending_upload_count == 1

    uploads.outcomes = [400, 200]
    manager._publish_snapshot(_snapshot(1, 2000))
    assert manager._drain_uploads() is True
    assert manager.pending_upload_count == 0
    assert len(uploads.calls) == 3


def test_every_2xx_is_done_and_timeouts_and_throttling_retry(uploads) -> None:
    manager = _manager()

    uploads.outcomes = [201]
    manager._publish_snapshot(_snapshot(1, 1000))
    assert manager._drain_uploads() is True
    assert manager.pending_upload_count == 0

    for status in (408, 429):
        uploads.outcomes = [status]
        manager._publish_snapshot(_snapshot(1, 2000))
        assert manager._drain_uploads() is False
        assert manager.pending_upload_count == 1
        uploads.outcomes = [200]
        assert manager._drain_uploads() is True
        assert manager.pending_upload_count == 0


def test_a_404_inside_an_http_200_is_not_a_success(uploads, caplog) -> None:
    manager = _manager()

    uploads.outcomes = [wrapped(404, "No data points found in your request")]
    manager._publish_snapshot(_snapshot(1, 1000))
    with caplog.at_level("ERROR"):
        manager._drain_uploads()

    assert manager.pending_upload_count == 0  # rejected, not kept: a retry would not help
    assert "404 (inside HTTP 200)" in caplog.text
    assert "No data points found" in caplog.text


def test_a_server_error_makes_the_requests_smaller_and_success_makes_them_large_again(
    uploads,
) -> None:
    manager = _manager(gathering_interval_seconds=10)
    for k in range(5):  # 5 snapshots 100 s apart: one chunk of 401 s
        manager._publish_snapshot(_snapshot(1, k * 100_000))
    assert manager._chunk_seconds == 600

    uploads.outcomes = [503]
    assert manager._drain_uploads() is False
    assert manager._chunk_seconds == 300  # the server did not like the big request
    assert manager.pending_upload_count == 5  # nothing was lost

    uploads.outcomes = [200, 200]
    assert manager._drain_uploads() is True
    assert manager.pending_upload_count == 0
    assert [_seconds(c) for c in uploads.calls] == [
        [0, 100, 200, 300, 400],  # the request the server refused
        [0, 100, 200],  # the same data, first 300 s
        [300, 400],  # and the rest
    ]
    assert manager._chunk_seconds == 600  # it doubled with each success


def test_a_network_error_does_not_make_the_requests_smaller(uploads) -> None:
    manager = _manager(gathering_interval_seconds=10)
    for k in range(3):
        manager._publish_snapshot(_snapshot(1, k * 100_000))

    uploads.outcomes = [ConnectionError("no route")]
    manager._drain_uploads()

    assert manager._chunk_seconds == 600


def _rows(start_s: int, serials=(1, 2, 3), seconds: int = 30) -> dict[int, pd.DataFrame]:
    """`seconds` rows for every device, as the manager gathers them (ms index)."""
    index = pd.Index([(start_s + i) * 1000 for i in range(seconds)], name="unix_timestamp")
    return {sn: pd.DataFrame({"ldsa": 1.0}, index=index) for sn in serials}


def test_requests_carry_at_most_max_chunk_rows_of_all_devices(monkeypatch, uploads) -> None:
    monkeypatch.setattr(NaneosDeviceManager, "MAX_CHUNK_ROWS", 100)
    manager = _manager()
    for k in range(4):  # 3 devices x 30 s x 4 snapshots = 360 rows in one chunk
        manager._publish_snapshot(_rows(1000 + 30 * k))
    uploads.outcomes = [200] * 10

    assert manager._drain_uploads() is True

    sizes = [sum(len(df) for df in call.values()) for call in uploads.calls]
    assert sum(sizes) == 360  # all of it went out
    assert len(sizes) >= 4 and max(sizes) <= 105  # about 100 rows, not one request of 360


def test_a_slow_server_makes_the_requests_smaller_but_a_lost_connection_does_not(uploads) -> None:
    manager = _manager(gathering_interval_seconds=10)
    for k in range(5):
        manager._publish_snapshot(_snapshot(1, k * 100_000))

    uploads.outcomes = [requests.ConnectTimeout("no connection")]
    manager._drain_uploads()
    assert manager._chunk_seconds == 600  # the network, not the size

    uploads.outcomes = [requests.ReadTimeout("the server did not answer")]
    assert manager._drain_uploads() is False
    assert manager._chunk_seconds == 300  # reached, but too slow for this size
    assert manager.pending_upload_count == 5  # nothing lost


def test_a_rejected_diagnostic_does_not_hold_up_the_ones_behind_it(monkeypatch, caplog) -> None:
    form = PulseForm(DeviceType.P2, 8617, 1_700_000_001, (0.0, 0.06))
    curve = UiCurve(DeviceType.P2, 8617, 1_700_000_000, (0, 498), (0.0, 0.5))
    answers = [wrapped(404, "No data points found in your request"), FakeResponse(200)]
    sent = []
    monkeypatch.setattr(
        module, "upload_diagnostic", lambda item: sent.append(item) or answers.pop(0)
    )
    manager = _manager()
    manager._pending_diagnostics.extend([form, curve])

    with caplog.at_level("ERROR"):
        manager._drain_uploads()

    assert sent == [form, curve]
    assert manager.pending_diagnostics_count == 0
    assert "dropping PulseForm" in caplog.text


def test_a_failing_diagnostics_endpoint_does_not_delay_the_snapshots(monkeypatch, uploads) -> None:
    form = PulseForm(DeviceType.P2, 8617, 1_700_000_001, (0.0, 0.06))
    monkeypatch.setattr(module, "upload_diagnostic", lambda item: FakeResponse(502))
    manager = _manager()
    manager._pending_diagnostics.append(form)
    uploads.outcomes = [200]
    manager._publish_snapshot(_snapshot(1, 1000))

    assert manager._drain_uploads() is True  # the snapshot went out ...
    assert manager.pending_upload_count == 0
    assert manager.pending_diagnostics_count == 1  # ... the form waits for its own pause
    assert manager._diagnostics_retry_at > time.monotonic()


def test_the_buffer_is_capped_in_bytes_and_the_oldest_data_goes(uploads, caplog) -> None:
    manager = _manager(upload_buffer_mb=0.01)  # room for two small chunks

    with caplog.at_level("WARNING"):
        for k in range(10):  # 700 s apart: every snapshot is a chunk of its own
            manager._publish_snapshot(_snapshot(1, k * 700_000))

    assert 1 <= manager.pending_upload_count <= 3
    assert manager.pending_upload_bytes <= 0.01e6 + 5000  # soft by the size of one chunk
    assert "Upload buffer is full" in caplog.text
    kept = []
    uploads.outcomes = [200] * 10
    manager._drain_uploads()
    kept = [_seconds(c)[0] for c in uploads.calls]
    assert kept[-1] == 9 * 700  # the newest survived, the oldest are gone
    assert kept[0] > 0


def test_a_snapshot_the_upload_cannot_read_is_skipped_without_stopping_the_gathering(
    monkeypatch, uploads, caplog
) -> None:
    def broken(data):
        raise ValueError("cannot read this frame")

    monkeypatch.setattr(module, "prepare_frames", broken)
    manager = _manager()
    out_q: queue.Queue = queue.Queue()
    manager.register_output_queue(out_q)

    with caplog.at_level("ERROR"):
        manager._publish_snapshot(_snapshot(1, 1000))  # must not raise

    assert list(out_q.get_nowait()) == [1]  # the customer still gets the snapshot
    assert manager.pending_upload_count == 0
    assert "Could not keep a snapshot for the upload" in caplog.text


def test_upload_buffer_mb_must_be_positive() -> None:
    for bad in (0, -1, float("nan")):
        with pytest.raises(ValueError):
            _manager(upload_buffer_mb=bad)


def test_empty_snapshot_and_disabled_upload_do_not_queue(uploads) -> None:
    out_q: queue.Queue = queue.Queue()
    manager = NaneosDeviceManager(use_serial=False, use_ble=False, upload_active=False)
    manager.register_output_queue(out_q)

    manager._publish_snapshot(_snapshot(1, 1000))
    assert list(out_q.get_nowait()) == [1]  # the queue receives it regardless
    assert manager.pending_upload_count == 0

    manager.upload_active = True
    manager._publish_snapshot({})
    assert manager.pending_upload_count == 0
    assert uploads.calls == []


def test_the_sender_thread_survives_an_outage_and_sends_what_was_kept(monkeypatch, uploads) -> None:
    monkeypatch.setattr(NaneosDeviceManager, "RETRY_DELAYS_SECONDS", (0.02, 0.05))
    manager = _manager()
    uploads.outcomes = [ConnectionError("down"), ConnectionError("down"), 200, 200]
    sender = threading.Thread(target=manager._sender_loop, daemon=True)
    sender.start()
    try:
        manager._publish_snapshot(_snapshot(1, 1000))
        manager._publish_snapshot(_snapshot(1, 31_000))

        deadline = time.time() + 5
        while time.time() < deadline and manager.pending_upload_count:
            time.sleep(0.01)
        assert manager.pending_upload_count == 0
        assert len(uploads.calls) >= 3  # two failures, then the data
    finally:
        manager.stop()
        sender.join(timeout=5)
    assert not sender.is_alive()


def test_the_sender_thread_stays_alive_when_a_send_raises_something_unexpected(
    monkeypatch,
) -> None:
    monkeypatch.setattr(NaneosDeviceManager, "RETRY_DELAYS_SECONDS", (0.02,))
    manager = _manager()
    calls = []

    def broken(frames):
        calls.append(frames)
        if len(calls) == 1:
            raise RuntimeError("bug in a send")
        return FakeResponse(200)

    monkeypatch.setattr(module, "send_frames", broken)
    sender = threading.Thread(target=manager._sender_loop, daemon=True)
    sender.start()
    try:
        manager._publish_snapshot(_snapshot(1, 1000))
        deadline = time.time() + 5
        while time.time() < deadline and len(calls) < 2:
            time.sleep(0.01)
        assert len(calls) == 2  # the thread went on and sent it
    finally:
        manager.stop()
        sender.join(timeout=5)


def test_start_runs_the_sender_next_to_the_loop_and_stop_ends_both(uploads) -> None:
    manager = _manager()
    uploads.outcomes = [200]

    manager.start()
    try:
        deadline = time.time() + 5
        while time.time() < deadline and (
            manager._sender is None or not manager._sender.is_alive()
        ):
            time.sleep(0.01)
        assert manager._sender is not None and manager._sender.name == "naneos-upload"

        manager._publish_snapshot(_snapshot(1, 1000))
        deadline = time.time() + 5
        while time.time() < deadline and not uploads.calls:
            time.sleep(0.01)
        assert len(uploads.calls) == 1  # sent by the thread, nobody called _drain_uploads()
    finally:
        manager.stop()
        manager.join(timeout=10)

    assert not manager.is_alive()
    assert not manager._sender.is_alive()

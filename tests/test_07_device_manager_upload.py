"""Hardware-free tests for the upload retry buffer of NaneosDeviceManager."""

import queue
from types import SimpleNamespace

import pandas as pd
import pytest

from naneos import manager as module
from naneos.manager import NaneosDeviceManager


def _snapshot(serial: int, ts: int) -> dict[int, pd.DataFrame]:
    df = pd.DataFrame({"unix_timestamp": [ts], "ldsa": [1.0]}).set_index("unix_timestamp")
    return {serial: df}


@pytest.fixture
def uploads(monkeypatch):
    """Replace the network call; `outcomes` is consumed one entry per attempt."""
    state = SimpleNamespace(outcomes=[], calls=[])

    def fake_upload(data):
        state.calls.append(data)
        outcome = state.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(status_code=outcome)

    monkeypatch.setattr(module, "upload_snapshot", fake_upload)
    return state


def test_failed_snapshot_is_kept_and_sent_on_the_next_tick(uploads) -> None:
    manager = NaneosDeviceManager(use_serial=False, use_ble=False, upload_active=True)

    uploads.outcomes = [ConnectionError("no network")]
    manager._publish_snapshot(_snapshot(1, 1000))
    assert manager.pending_upload_count == 1

    uploads.outcomes = [200, 200]
    manager._publish_snapshot(_snapshot(1, 2000))

    assert manager.pending_upload_count == 0
    assert [list(c[1].index)[0] for c in uploads.calls] == [1000, 1000, 2000]


def test_server_errors_retry_but_client_errors_drop(uploads) -> None:
    manager = NaneosDeviceManager(use_serial=False, use_ble=False, upload_active=True)

    uploads.outcomes = [503]
    manager._publish_snapshot(_snapshot(1, 1000))
    assert manager.pending_upload_count == 1

    uploads.outcomes = [400, 200]
    manager._publish_snapshot(_snapshot(1, 2000))
    assert manager.pending_upload_count == 0
    assert len(uploads.calls) == 3


def test_buffer_is_bounded_and_oldest_snapshots_are_dropped(uploads) -> None:
    manager = NaneosDeviceManager(use_serial=False, use_ble=False, upload_active=True)

    for ts in range(NaneosDeviceManager.MAX_PENDING_UPLOADS + 5):
        uploads.outcomes = [ConnectionError("no network")]
        manager._publish_snapshot(_snapshot(1, ts))

    assert manager.pending_upload_count == NaneosDeviceManager.MAX_PENDING_UPLOADS
    assert list(manager._pending_uploads[0][1].index) == [5]


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

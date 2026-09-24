"""Hardware-free tests for the RAM backlog of the upload."""

import threading

import numpy as np
import pandas as pd

from naneos.cloud.backlog import CHUNK_SECONDS, UploadBacklog

T0 = 1_780_000_000


def snapshot(start: int, seconds: int = 30, serials=(1,)) -> dict[int, pd.DataFrame]:
    """One snapshot: a row per second and device, as prepare_frames leaves them."""
    index = pd.Index(np.arange(start, start + seconds, dtype="int64"), name="unix_timestamp")
    return {
        sn: pd.DataFrame({"ldsa": np.arange(seconds, dtype="float64")}, index=index)
        for sn in serials
    }


def rows(chunk) -> int:
    return sum(len(df) for df in chunk.frames.values())


def test_snapshots_are_merged_into_chunks_of_up_to_600_seconds() -> None:
    backlog = UploadBacklog(max_bytes=10**9)

    for k in range(20):
        backlog.add(snapshot(T0 + 30 * k))
    assert len(backlog) == 1
    assert backlog.snapshots == 20
    assert backlog.seconds == CHUNK_SECONDS

    backlog.add(snapshot(T0 + 600))  # would make the chunk longer than 600 s
    assert len(backlog) == 2
    assert backlog.snapshots == 21


def test_a_chunk_that_was_taken_is_never_merged_into() -> None:
    backlog = UploadBacklog(max_bytes=10**9)
    backlog.add(snapshot(T0))

    first = backlog.take()
    assert first is not None and first.sealed and rows(first) == 30
    assert len(backlog) == 0 and backlog.size_bytes == 0

    backlog.add(snapshot(T0 + 30))
    backlog.restore(first)  # a failed send: back to the head
    backlog.add(snapshot(T0 + 60))

    assert [c.first for c in (backlog.take(), backlog.take())] == [T0, T0 + 30]  # type: ignore[union-attr]


def test_take_can_cut_a_chunk_and_leaves_the_rest_in_place() -> None:
    backlog = UploadBacklog(max_bytes=10**9)
    for k in range(20):
        backlog.add(snapshot(T0 + 30 * k, serials=(1, 2)))
    total = backlog.snapshots

    piece = backlog.take(max_seconds=150)
    assert piece is not None
    assert (piece.first, piece.last) == (T0, T0 + 149)
    assert all(len(df) == 150 for df in piece.frames.values())
    assert len(backlog) == 1 and backlog.seconds == 450  # the rest is still the head chunk
    assert piece.snapshots + backlog.snapshots == total

    rest = backlog.take()
    assert rest is not None and (rest.first, rest.last) == (T0 + 150, T0 + 599)
    joined = pd.concat([piece.frames[1], rest.frames[1]])
    assert list(joined.index) == list(range(T0, T0 + 600))  # nothing lost, nothing twice


def test_the_oldest_chunks_go_first_when_the_cap_is_reached() -> None:
    probe = UploadBacklog(max_bytes=10**9)
    probe.add(snapshot(T0, seconds=600))
    one_chunk = probe.size_bytes

    backlog = UploadBacklog(max_bytes=int(one_chunk * 2.5))
    evicted = None
    for k in range(5):
        evicted = backlog.add(snapshot(T0 + 600 * k, seconds=600)) or evicted

    assert len(backlog) == 2
    assert backlog.size_bytes <= one_chunk * 2.5
    assert evicted is not None
    first = backlog.take()
    assert first is not None and first.first == T0 + 600 * 3  # 0, 1 and 2 were dropped

    total_dropped = 0
    fresh = UploadBacklog(max_bytes=int(one_chunk * 1.5))
    for k in range(4):
        result = fresh.add(snapshot(T0 + 600 * k, seconds=600))
        total_dropped += result.snapshots if result else 0
    assert total_dropped == 3  # each dropped chunk held one snapshot


def test_the_newest_chunk_stays_even_when_it_alone_is_over_the_cap() -> None:
    backlog = UploadBacklog(max_bytes=1)

    backlog.add(snapshot(T0))
    backlog.add(snapshot(T0 + 600))

    assert len(backlog) == 1
    chunk = backlog.take()
    assert chunk is not None and chunk.first == T0 + 600


def test_rows_of_the_same_second_in_two_snapshots_become_one_row() -> None:
    backlog = UploadBacklog(max_bytes=10**9)
    backlog.add(snapshot(T0, seconds=10))
    backlog.add(snapshot(T0 + 9, seconds=10))  # its first second is the last one of the first

    chunk = backlog.take()
    assert chunk is not None
    assert list(chunk.frames[1].index) == list(range(T0, T0 + 19))


def test_a_snapshot_without_rows_is_ignored() -> None:
    backlog = UploadBacklog(max_bytes=10**9)

    assert backlog.add({}) is None
    assert backlog.add({1: snapshot(T0)[1].iloc[0:0]}) is None
    assert len(backlog) == 0 and backlog.take() is None


def test_bytes_follow_what_is_kept() -> None:
    backlog = UploadBacklog(max_bytes=10**9)
    backlog.add(snapshot(T0))
    one = backlog.size_bytes
    backlog.add(snapshot(T0 + 600))
    assert backlog.size_bytes > one

    assert backlog.take() is not None
    assert backlog.size_bytes == one  # the second chunk has the shape of the first
    assert backlog.take() is not None
    assert backlog.size_bytes == 0


def test_one_thread_adds_while_another_takes_and_nothing_is_lost() -> None:
    backlog = UploadBacklog(max_bytes=10**9)
    taken_rows = 0
    done = threading.Event()

    def writer() -> None:
        for k in range(300):
            backlog.add(snapshot(T0 + 30 * k))
        done.set()

    def reader() -> None:
        nonlocal taken_rows
        while not (done.is_set() and len(backlog) == 0):
            chunk = backlog.take(max_seconds=100)
            if chunk is not None:
                taken_rows += rows(chunk)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert taken_rows == 300 * 30


def test_take_limits_a_chunk_by_rows_of_all_devices_together() -> None:
    backlog = UploadBacklog(max_bytes=10**9)
    for k in range(20):  # 600 s of three devices: 1800 rows
        backlog.add(snapshot(T0 + 30 * k, serials=(1, 2, 3)))

    piece = backlog.take(max_seconds=600, max_rows=600)

    assert piece is not None
    assert piece.rows == 600 and piece.seconds == 200  # 3 rows per second
    rest = backlog.take()
    assert rest is not None and rest.rows == 1200 and rest.first == T0 + 200


def test_a_chunk_within_the_row_limit_is_taken_whole() -> None:
    backlog = UploadBacklog(max_bytes=10**9)
    backlog.add(snapshot(T0, seconds=100, serials=(1, 2)))

    chunk = backlog.take(max_seconds=600, max_rows=1000)

    assert chunk is not None and chunk.rows == 200 and len(backlog) == 0

"""Data waiting for the upload, kept in RAM, capped in bytes.

While the network is down the manager keeps what it gathers here and the sender
takes it out again, oldest first. The frames are the ones the upload reads
(see upload.prepare_frames: one row per second, only the columns that go on the
wire), so they are small, and they stay frames so that the sender can merge them
into as large a request as the backend is used to.

Snapshots are merged into chunks of up to CHUNK_SECONDS of data. A pandas frame
has a fixed overhead of about 5 KB, which is more than the data of a 30 s
snapshot of one device: kept one by one, a day would cost about 80 % on top of
the data, in chunks of 600 s less than 10 %.
"""

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import NamedTuple

import pandas as pd

from naneos.frames import aggregate_duplicate_index

# The largest snapshot a customer can ask for today (--interval 600).
CHUNK_SECONDS = 600
# Measured fixed cost of one DataFrame of numpy columns (two blocks), on top of its data.
FRAME_OVERHEAD_BYTES = 5120


class Eviction(NamedTuple):
    """What a full buffer threw away."""

    snapshots: int
    seconds: int  # of data, counted per chunk (devices in parallel are not added up)


@dataclass
class Chunk:
    """The frames of up to CHUNK_SECONDS of data, indexed by unix seconds."""

    frames: dict[int, pd.DataFrame]
    first: int  # unix seconds of the first row of any device
    last: int
    snapshots: int = 1  # how many snapshots were merged into it
    sealed: bool = False  # taken once: nothing is merged into it any more
    nbytes: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.nbytes = _size_of(self.frames)

    @property
    def seconds(self) -> int:
        return self.last - self.first + 1

    @property
    def rows(self) -> int:
        """The rows of all devices: what the backend has to write for this chunk."""
        return sum(len(df) for df in self.frames.values())


def _size_of(frames: dict[int, pd.DataFrame]) -> int:
    return sum(
        int(df.memory_usage(index=True).sum()) + FRAME_OVERHEAD_BYTES for df in frames.values()
    )


class UploadBacklog:
    """A FIFO of chunks, thread-safe: the manager adds, the sender takes.

    Args:
        max_bytes: the cap. It is soft by one chunk: the newest chunk is never
            evicted, so a cap below the size of one chunk still keeps the latest data.
        chunk_seconds: the most data merged into one chunk.
    """

    def __init__(self, max_bytes: int, chunk_seconds: int = CHUNK_SECONDS) -> None:
        self._max_bytes = max_bytes
        self._chunk_seconds = chunk_seconds
        self._chunks: deque[Chunk] = deque()
        self._bytes = 0
        self._lock = threading.Lock()

    def add(self, frames: dict[int, pd.DataFrame]) -> Eviction | None:
        """Keep the frames of one snapshot. Returns what had to go to stay under the cap."""
        frames = {sn: df for sn, df in frames.items() if not df.empty}
        if not frames:
            return None
        first = min(int(df.index.min()) for df in frames.values())
        last = max(int(df.index.max()) for df in frames.values())

        with self._lock:
            tail = self._chunks[-1] if self._chunks else None
            if tail is not None and not tail.sealed and last - tail.first < self._chunk_seconds:
                self._bytes -= tail.nbytes
                self._merge(tail, frames, last)
                self._bytes += tail.nbytes
            else:
                chunk = Chunk(frames, first, last)
                self._chunks.append(chunk)
                self._bytes += chunk.nbytes
            return self._evict()

    def take(self, max_seconds: int | None = None, max_rows: int | None = None) -> Chunk | None:
        """Remove and return the oldest chunk, or the first part of it.

        The part is at most `max_seconds` long and holds about `max_rows` rows (all
        devices together; the rows are taken to be spread evenly over the time).
        What the caller could not send goes back with restore().
        """
        with self._lock:
            if not self._chunks:
                return None
            chunk = self._chunks.popleft()
            self._bytes -= chunk.nbytes
            chunk.sealed = True

            limit = chunk.seconds if max_seconds is None else max_seconds
            if max_rows is not None and chunk.rows > max_rows:
                limit = min(limit, max(1, int(chunk.seconds * max_rows / chunk.rows)))
            if chunk.seconds > limit:
                chunk, rest = _split(chunk, chunk.first + limit)
                self._chunks.appendleft(rest)
                self._bytes += rest.nbytes
            return chunk

    def restore(self, chunk: Chunk) -> Eviction | None:
        """Put a chunk that could not be sent back at the head."""
        with self._lock:
            chunk.sealed = True
            self._chunks.appendleft(chunk)
            self._bytes += chunk.nbytes
            return self._evict()

    @property
    def size_bytes(self) -> int:
        return self._bytes

    @property
    def snapshots(self) -> int:
        """The number of snapshots waiting."""
        with self._lock:
            return sum(chunk.snapshots for chunk in self._chunks)

    @property
    def seconds(self) -> int:
        """Seconds of data waiting, counted per chunk."""
        with self._lock:
            return sum(chunk.seconds for chunk in self._chunks)

    def __len__(self) -> int:
        return len(self._chunks)

    @staticmethod
    def _merge(tail: Chunk, frames: dict[int, pd.DataFrame], last: int) -> None:
        for sn, df in frames.items():
            known = tail.frames.get(sn)
            if known is None:
                tail.frames[sn] = df
            else:
                merged = pd.concat([known, df])
                # A 10 or 100 Hz device can put rows of two snapshots into the same second.
                tail.frames[sn] = aggregate_duplicate_index(merged)
        tail.last = max(tail.last, last)
        tail.snapshots += 1
        tail.nbytes = _size_of(tail.frames)

    def _evict(self) -> Eviction | None:
        """Drop the oldest chunks while over the cap; the caller holds the lock."""
        snapshots = seconds = 0
        while self._bytes > self._max_bytes and len(self._chunks) > 1:
            dropped = self._chunks.popleft()
            self._bytes -= dropped.nbytes
            snapshots += dropped.snapshots
            seconds += dropped.seconds
        return Eviction(snapshots, seconds) if snapshots else None


def _split(chunk: Chunk, boundary: int) -> tuple[Chunk, Chunk]:
    """The rows before `boundary` and the rest, as two chunks."""
    head = {sn: df[df.index < boundary] for sn, df in chunk.frames.items()}
    tail = {sn: df[df.index >= boundary] for sn, df in chunk.frames.items()}
    head = {sn: df for sn, df in head.items() if not df.empty}
    tail = {sn: df for sn, df in tail.items() if not df.empty}

    total = chunk.seconds
    head_share = min(
        max(round(chunk.snapshots * (boundary - chunk.first) / total), 1), chunk.snapshots
    )
    first_of_tail = min(int(df.index.min()) for df in tail.values()) if tail else boundary
    last_of_head = max(int(df.index.max()) for df in head.values()) if head else chunk.first

    piece = Chunk(head, chunk.first, last_of_head, head_share, sealed=True)
    rest = Chunk(tail, first_of_tail, chunk.last, max(chunk.snapshots - head_share, 1), sealed=True)
    return piece, rest

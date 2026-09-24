"""Commands to a Partector over BLE: the same ASCII protocol as on USB.

A command is written to the "write" characteristic; the answer arrives as an
indication on "read" (it cannot be read), in 20 byte frames: the text, "\\r\\n",
padded with spaces. Measured answer times are 0.25 s to 1 s.

An answer carries no reference to its command. One command is in flight per
device, and the answer is the first one that arrives after the command was
written; a caller that knows what its answer looks like says so with `accept`,
so that a late answer to an earlier command is not taken for it.
"""

import asyncio
from collections.abc import Awaitable, Callable

from bleak.exc import BleakError


class BleCommandChannel:
    """The write / query side of one BLE link. Must be used on the connection's event loop.

    Args:
        serial_number: only for the messages.
        write_frame: writes the bytes of one command to the write characteristic
            of the current link.
        is_connected: True while there is a link to write to.
    """

    MAX_COMMAND_BYTES = 20  # what one write of the characteristic takes
    QUERY_TIMEOUT_SECONDS = 2.0

    def __init__(
        self,
        serial_number: int,
        write_frame: Callable[[bytes], Awaitable[None]],
        is_connected: Callable[[], bool],
    ) -> None:
        self._serial_number = serial_number
        self._write_frame = write_frame
        self._is_connected = is_connected

        # Held while a command is in flight, and by a diagnostics readout for as
        # long as it collects its packets.
        self.lock = asyncio.Lock()
        # False for a device without the command characteristics: its data still flows.
        self.available = False

        self._replies: asyncio.Queue[list[str]] = asyncio.Queue()
        self._buffer = b""

    async def write(self, command: str) -> None:
        """Send a command that has no answer.

        Raises:
            ConnectionError: there is no link, or the device has no command characteristic.
            ValueError: the command does not fit into one write.
        """
        async with self.lock:
            await self.write_locked(command)

    async def query(
        self,
        command: str,
        timeout: float | None = None,
        accept: Callable[[list[str]], bool] | None = None,
    ) -> list[str]:
        """Send a command and return the tab separated fields of its answer.

        Args:
            timeout: seconds to wait for the answer, QUERY_TIMEOUT_SECONDS by default.
            accept: tells the answer to this command from a late answer to an
                earlier one; answers it rejects are skipped. Without it the
                first answer counts.

        Raises:
            ConnectionError, ValueError: see write().
            TimeoutError: no accepted answer within timeout.
        """
        loop = asyncio.get_running_loop()
        async with self.lock:
            self._buffer = b""
            while not self._replies.empty():
                self._replies.get_nowait()

            await self.write_locked(command)
            deadline = loop.time() + (timeout or self.QUERY_TIMEOUT_SECONDS)
            while True:
                try:
                    fields = await asyncio.wait_for(self._replies.get(), deadline - loop.time())
                except TimeoutError:
                    raise TimeoutError(
                        f"SN{self._serial_number}: no answer to {command!r}."
                    ) from None
                if accept is None or accept(fields):
                    return fields

    async def write_locked(self, command: str) -> None:
        """Like write(), for a caller that holds the lock."""
        data = command.encode()
        if len(data) > self.MAX_COMMAND_BYTES:
            raise ValueError(f"A BLE command is limited to {self.MAX_COMMAND_BYTES} bytes.")
        if not self._is_connected():
            raise ConnectionError(f"SN{self._serial_number} is not connected.")
        if not self.available:
            raise ConnectionError(f"SN{self._serial_number} does not accept commands over BLE.")

        try:
            await self._write_frame(data)
        except (BleakError, OSError) as e:
            raise ConnectionError(f"SN{self._serial_number}: write failed: {e}") from e

    def on_reply_frame(self, data: bytes) -> None:
        """A frame on the read characteristic (event loop thread).

        An answer ends with a line end; what follows in that frame is padding.
        """
        self._buffer += data
        if b"\n" not in self._buffer:
            return  # a longer answer continues in the next frame

        line = self._buffer.split(b"\n", 1)[0].decode(errors="replace").strip("\r ")
        self._buffer = b""
        self._replies.put_nowait(line.split("\t"))

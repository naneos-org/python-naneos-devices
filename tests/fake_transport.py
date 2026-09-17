"""A SerialTransport without a port, for the hardware-free serial tests."""

import queue


class FakeTransport:
    """Answers the queries of a Partector and lets a test feed verbose lines."""

    def __init__(self, serial_number: int = 8617, firmware: int = 422, name: str = "P2") -> None:
        self.port = "/dev/fake"
        self.answers = {"N?": str(serial_number), "f?": str(firmware), "H?": "1", "name?": name}
        self.written: list[str] = []
        self.mute = False  # a device that stopped answering
        self._lines: queue.Queue[str] = queue.Queue()
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def unplug(self) -> None:
        self._open = False

    def write(self, command: str) -> None:
        if not self._open:
            raise ConnectionError("fake port is closed")
        self.written.append(command)
        if command in self.answers and not self.mute:
            self._lines.put(self.answers[command])

    def readline(self) -> str:
        if not self._open:
            raise ConnectionError("fake port is closed")
        try:
            return self._lines.get(timeout=0.01)
        except queue.Empty:
            return ""

    def discard_input(self) -> None:
        while not self._lines.empty():
            self._lines.get_nowait()

    def emit(self, columns: int, value: str = "1") -> None:
        """Feed a verbose line with this many tab separated columns."""
        self._lines.put("\t".join([value] * columns))

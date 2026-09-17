"""The serial port of one Partector: open, write, read a line, close. No threads."""

import time

import serial


class SerialTransport:
    # The port is USB CDC, so the baudrate is only a formality.
    BAUDRATE = 9600
    # How long readline() waits for a line. Also bounds how fast a reader
    # thread notices that it should stop.
    READ_TIMEOUT_SECONDS = 0.2
    # A device streaming at 100 Hz can make open() fail transiently.
    OPEN_TIMEOUT_SECONDS = 0.5

    def __init__(self, port: str) -> None:
        self.port = port
        self._ser: serial.Serial | None = None

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def open(self) -> None:
        """Raises ConnectionError if the port cannot be opened."""
        deadline = time.monotonic() + self.OPEN_TIMEOUT_SECONDS
        error: Exception | None = None

        while True:
            try:
                self._ser = serial.Serial(
                    port=self.port, baudrate=self.BAUDRATE, timeout=self.READ_TIMEOUT_SECONDS
                )
                return
            except (OSError, serial.SerialException) as e:
                error = e
            if time.monotonic() >= deadline:
                raise ConnectionError(f"Could not open {self.port}: {error}") from error
            time.sleep(0.01)

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except (OSError, serial.SerialException):
                pass  # an unplugged port cannot be closed any more than it already is

    def write(self, command: str) -> None:
        """Raises ConnectionError if the port is gone."""
        if self._ser is None or not self._ser.is_open:
            raise ConnectionError(f"{self.port} is not open.")
        try:
            self._ser.write(command.encode())
        except (OSError, serial.SerialException) as e:
            raise ConnectionError(f"Could not write to {self.port}: {e}") from e

    def readline(self) -> str:
        """One line without its line end; "" if none arrived within the timeout.

        Raises ConnectionError if the port is gone.
        """
        if self._ser is None or not self._ser.is_open:
            raise ConnectionError(f"{self.port} is not open.")
        try:
            raw = self._ser.readline()
        except (OSError, serial.SerialException, TypeError) as e:
            # TypeError: pyserial on POSIX when the port is closed under a read.
            raise ConnectionError(f"Could not read from {self.port}: {e}") from e
        return raw.decode(errors="replace").replace("\r", "").replace("\n", "").replace("\x00", "")

    def discard_input(self) -> None:
        if self._ser is not None and self._ser.is_open:
            try:
                self._ser.reset_input_buffer()
            except (OSError, serial.SerialException):
                pass

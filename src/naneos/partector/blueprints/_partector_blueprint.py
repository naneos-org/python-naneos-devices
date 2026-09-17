import queue
import time
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from threading import Event, Lock, Thread, current_thread
from typing import ClassVar, TypeVar

from naneos.data_point import ConnectionType, DeviceType, NaneosDeviceDataPoint
from naneos.device import PartectorDevice
from naneos.logger import get_naneos_logger
from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_GAIN_TEST_ADDITIONAL_DATA_STRUCTURE,
    PARTECTOR2_OUTPUT_PULSE_DIAGNOSTIC_ADDITIONAL_DATA_STRUCTURE,
    SerialLayout,
)
from naneos.partector.serial_transport import SerialTransport

logger = get_naneos_logger(__name__)

T = TypeVar("T")


class PartectorBlueprint(PartectorDevice, ABC):
    """A Partector on USB. The device specific parts live in the child classes.

    A reader thread owns the input of the port: it turns the verbose lines into
    data points and hands every other line to the query() that is waiting for
    it. The device does not reconnect on its own. Once is_connected is False it
    stays that way: close it and create a new one (PartectorSerialManager does).
    """

    DEVICE_TYPE: ClassVar[DeviceType]

    # The "X000n!" code behind each rate.
    SAMPLE_RATE_CODES: ClassVar[dict[int, int]] = {0: 0, 1: 1, 10: 2, 100: 3}

    QUERY_TIMEOUT_SECONDS = 0.25
    # Used for the queries of this class only, which are safe to repeat.
    QUERY_RETRIES = 7
    # Parsed points waiting for get_data(): ten seconds at 100 Hz.
    DATA_QUEUE_MAXSIZE = 1000
    # A silent device is asked for its serial number to see if it is still there.
    SILENCE_BEFORE_PROBE_SECONDS = 10.0
    PROBE_TIMEOUT_SECONDS = 1.0
    PORT_SCAN_RETRIES = 5

    def __init__(
        self,
        serial_number: int | None = None,
        port: str | None = None,
        sample_rate_hz: int = 1,
        transport: SerialTransport | None = None,
    ) -> None:
        """Opens the port, identifies the device, configures it and starts the output.

        Args:
            serial_number: find the device with this serial number on the USB ports.
            port: use this port instead of searching for the serial number.
            sample_rate_hz: 0 (no output), 1, 10 or 100.
            transport: an already constructed transport; replaces serial_number / port lookup.

        Raises:
            ValueError: neither serial_number nor port given.
            ConnectionError: the device was not found, did not answer, or is not
                the one with the requested serial number.
        """
        self._sn: int | None = None
        self._fw: int = 0
        self._integration_time: int = 0
        self._sample_rate_hz: float | None = 0
        self._connected = False

        # Set by the child class in _configure().
        self._data_structure: SerialLayout = {}
        self._legacy_data_structure = False
        self._gain_test_active = False
        self._pulse_diagnostics_active = False
        self._diagnostics_configured = False
        self._settled_at = 0.0  # time.time() from which data is trusted again

        self._points: deque[NaneosDeviceDataPoint] = deque(maxlen=self.DATA_QUEUE_MAXSIZE)
        self._replies: queue.Queue[list[str]] = queue.Queue()
        self._command_lock = Lock()
        self._stop_event = Event()
        self._last_line_at = time.monotonic()

        self._transport = transport or SerialTransport(self._find_port(serial_number, port))
        self._transport.open()
        self._connected = True
        self._silence()

        self._reader = Thread(
            target=self._reader_loop, name=f"naneos-serial-{self._transport.port}", daemon=True
        )
        self._reader.start()

        try:
            self._read_device_info(expected_serial_number=serial_number)
            self._configure()
            self._start_output(sample_rate_hz)
        except Exception:
            self.close(reset_device=False)
            raise

        logger.info(f"Connected to SN{self._sn} on {self._transport.port}")

    # == PartectorDevice ===========================================================================
    @property
    def serial_number(self) -> int | None:
        return self._sn

    @property
    def device_type(self) -> DeviceType:
        return self.DEVICE_TYPE

    @property
    def firmware_version(self) -> int:
        return self._fw

    @property
    def connection_type(self) -> ConnectionType:
        return ConnectionType.SERIAL

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def sample_rate_hz(self) -> float | None:
        return self._sample_rate_hz

    def write(self, command: str) -> None:
        with self._command_lock:
            self._write(command)

    def query(self, command: str, timeout: float | None = None) -> list[str]:
        if current_thread() is self._reader:
            raise RuntimeError("query() cannot be called from the reader thread.")

        with self._command_lock:
            self._drain_replies()
            self._write(command)
            try:
                return self._replies.get(timeout=timeout or self.QUERY_TIMEOUT_SECONDS)
            except queue.Empty:
                raise TimeoutError(f"SN{self._sn}: no answer to {command!r}.") from None

    def set_sample_rate(self, hz: int) -> None:
        if hz not in self.SAMPLE_RATE_CODES:
            raise ValueError(f"Sample rate must be one of {sorted(self.SAMPLE_RATE_CODES)} Hz.")
        self.write(f"X000{self.SAMPLE_RATE_CODES[hz]}!")
        self._sample_rate_hz = hz

    # == Serial specific API =======================================================================
    @property
    def port(self) -> str:
        return self._transport.port

    @property
    def integration_time_seconds(self) -> int:
        return self._integration_time

    @property
    def is_settling(self) -> bool:
        """True while the data is held back because a gain test was just started."""
        return time.time() < self._settled_at

    def get_data(self) -> list[NaneosDeviceDataPoint]:
        """Returns the data points received since the last call."""
        points: list[NaneosDeviceDataPoint] = []
        try:
            while True:
                points.append(self._points.popleft())
        except IndexError:
            pass
        return points

    def close(self, reset_device: bool = True) -> None:
        """Stops the reader thread and closes the port.

        Args:
            reset_device: switch the output and the diagnostics off first, which is
                how a device is normally left behind.
        """
        if reset_device and self._connected:
            try:
                self._reset_device()
            except ConnectionError as e:
                logger.debug(f"SN{self._sn}: could not reset the device on close: {e}")

        self._stop_event.set()
        if self._reader.is_alive() and current_thread() is not self._reader:
            self._reader.join()

    def power_off(self) -> None:
        """Switches the device off and closes the connection."""
        self.write("off!")
        self.close(reset_device=False)

    # == Device specific parts =====================================================================
    @abstractmethod
    def _configure(self) -> None:
        """Select self._data_structure for the firmware and send the device settings."""

    def _start_output(self, sample_rate_hz: int) -> None:
        self.set_sample_rate(sample_rate_hz)

    def _configure_diagnostics(self, gain_test: bool, pulse_diagnostics: bool) -> None:
        """Switch the optional P2 / P2 Pro output blocks on or off.

        The gain test disturbs the measurement for a while, so the data is held
        back until the device has settled. The columns the blocks append to a
        line come from _diagnostic_columns().
        """
        self._gain_test_active = gain_test
        self._pulse_diagnostics_active = pulse_diagnostics
        self._diagnostics_configured = True

        self.write("opd01!" if pulse_diagnostics else "opd00!")

        if gain_test:
            self._settled_at = time.time() + max(10, self._integration_time + 5)
            self.write("h2001!")  # activates harmonics output
            self.write("e1100!")  # strength of gain test signal
        else:
            self.write("h2000!")  # deactivates harmonics output
            self.write("e0000!")  # deactivates gain test signal

    def _diagnostic_columns(self) -> SerialLayout:
        columns: SerialLayout = {}
        if self._pulse_diagnostics_active:
            columns.update(PARTECTOR2_OUTPUT_PULSE_DIAGNOSTIC_ADDITIONAL_DATA_STRUCTURE)
        if self._gain_test_active:
            columns.update(PARTECTOR2_GAIN_TEST_ADDITIONAL_DATA_STRUCTURE)
        return columns

    def _reset_device(self) -> None:
        self.set_sample_rate(0)
        if self._diagnostics_configured:
            self.write("opd00!")
            self.write("h2000!")
            self.write("e0000!")

    # == Connecting ================================================================================
    def _find_port(self, serial_number: int | None, port: str | None) -> str:
        if port is not None:
            return port
        if serial_number is None:
            raise ValueError("No serial number or port given!")

        from naneos.partector.scan import scan_for_serial_partector

        for _ in range(self.PORT_SCAN_RETRIES):
            found = scan_for_serial_partector(serial_number, self.DEVICE_TYPE)
            if found:
                return found
        raise ConnectionError(f"SN{serial_number} not found on any serial port.")

    def _silence(self) -> None:
        """Stop the output so the first answers are not buried in data lines."""
        self._transport.write("X0000!")
        time.sleep(10e-3)
        self._transport.discard_input()

    def _read_device_info(self, expected_serial_number: int | None) -> None:
        self._sn = self._read_serial_number_secure()
        if expected_serial_number is not None and self._sn != expected_serial_number:
            raise ConnectionError(
                f"{self._transport.port} is SN{self._sn}, not SN{expected_serial_number}."
            )

        try:
            self._fw = self._query_with_retries("f?", lambda fields: int(fields[0]))
            # The device reports an exponent: 2 ** (n + 1) seconds.
            self._integration_time = self._query_with_retries(
                "H?", lambda fields: int(2 ** (int(fields[0]) + 1))
            )
        except (TimeoutError, ValueError) as e:
            logger.warning(f"SN{self._sn}: could not read the device info: {e}")

    def _read_serial_number_secure(self) -> int:
        """The serial number, once three reads in a row agree on it."""
        for _ in range(3):
            try:
                numbers = [
                    self._query_with_retries("N?", lambda fields: int(fields[0])) for _ in range(3)
                ]
            except TimeoutError:
                break  # already retried; nothing is listening
            except ValueError:
                continue
            if numbers[0] == numbers[1] == numbers[2]:
                return numbers[0]
        raise ConnectionError(f"No Partector answered on {self._transport.port}.")

    def _query_with_retries(self, command: str, parse: Callable[[list[str]], T]) -> T:
        """For queries that are safe to repeat. Raises the last error when all tries failed."""
        error: Exception = TimeoutError(f"No answer to {command!r}.")
        for _ in range(self.QUERY_RETRIES):
            try:
                return parse(self.query(command))
            except (TimeoutError, ValueError, IndexError) as e:
                error = e if isinstance(e, TimeoutError) else ValueError(str(e))
        raise error

    # == Reader thread =============================================================================
    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                line = self._transport.readline()
                if line:
                    self._handle_line(line)
                elif time.monotonic() - self._last_line_at > self.SILENCE_BEFORE_PROBE_SECONDS:
                    self._probe()
            except ConnectionError as e:
                if not self._stop_event.is_set():
                    logger.warning(f"SN{self._sn} on {self._transport.port}: connection lost: {e}")
                break
            except Exception as e:
                logger.warning(f"SN{self._sn} on {self._transport.port}: reader error: {e}")

        self._connected = False
        self._transport.close()

    def _handle_line(self, line: str) -> None:
        self._last_line_at = time.monotonic()
        unix_timestamp = int(time.time() * 1000)  # ms, like every other data source
        fields = line.split("\t")

        # The protocol has no framing: a verbose line is recognised by its
        # length, everything shorter is the answer to a command.
        layout = self._data_structure
        columns = len(fields) + 1  # the layout starts with the timestamp
        if not layout or columns < len(layout):
            self._replies.put(fields)
            return

        if time.time() < self._settled_at:
            return

        # Legacy mode: the exact layout is unknown, extra columns are cut off.
        if columns > len(layout) and not self._legacy_data_structure:
            return

        try:
            values: list[int | str] = [unix_timestamp, *fields[: len(layout) - 1]]
            self._points.append(self._create_naneos_device_point(layout, values))
        except ValueError as e:
            logger.warning(f"SN{self._sn}: could not parse {line!r}: {e}")

    def _probe(self) -> None:
        """Ask a silent device for its serial number. Raises ConnectionError if it is gone.

        Runs in the reader thread, which is the only one reading the port, so
        it collects the answer itself.
        """
        if not self._command_lock.acquire(blocking=False):
            return  # a query is in flight and will see for itself

        try:
            logger.info(f"SN{self._sn} {self._transport.port}: checking device connection...")
            self._drain_replies()
            self._transport.write("N?")

            deadline = time.monotonic() + self.PROBE_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                line = self._transport.readline()
                if line:
                    self._handle_line(line)
                try:
                    if self._replies.get_nowait() == [str(self._sn)]:
                        return
                except queue.Empty:
                    pass
        finally:
            self._command_lock.release()

        raise ConnectionError("the device does not answer any more.")

    # == Helpers ===================================================================================
    def _write(self, command: str) -> None:
        """Caller holds the command lock."""
        if not self._connected:
            raise ConnectionError(f"SN{self._sn} is not connected.")
        self._transport.write(command)

    def _drain_replies(self) -> None:
        try:
            while True:
                self._replies.get_nowait()
        except queue.Empty:
            pass

    def _create_naneos_device_point(
        self, layout: SerialLayout, values: list[int | str]
    ) -> NaneosDeviceDataPoint:
        point = NaneosDeviceDataPoint(
            device_type=self.DEVICE_TYPE,
            serial_number=self._sn,
            connection_type=ConnectionType.SERIAL,
            firmware_version=self._fw,
        )

        # Some serial columns (e.g. "lag", "flow_from_phase_angle") are parsed
        # only to match the line length and have no field on the data point.
        fields = NaneosDeviceDataPoint.__dataclass_fields__
        for (name, data_type), value in zip(layout.items(), values, strict=True):
            if name in fields:
                setattr(point, name, data_type(value))

        return point

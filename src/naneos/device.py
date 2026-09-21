"""The device API shared by every transport.

A Partector on USB and a Partector on a BLE link are used the same way:

    device.write("X0001!")            # a command without an answer
    fields = device.query("f?")       # a command with an answer -> ["422"]
    device.set_sample_rate(10)        # USB only, see NotSupportedError
    device.set_sample_rate(None)      # back to the default of the device
    curve = device.read_ui_curve()    # the two diagnostics, firmware 418 or newer
    form = device.read_pulse_form()
"""

from abc import ABC, abstractmethod

from naneos.data_point import ConnectionType, DeviceType
from naneos.diagnostics import PulseForm, UiCurve


class NotSupportedError(Exception):
    """The device or the transport it is reached over cannot do this."""


class PartectorDevice(ABC):
    """One Partector, whatever it is connected with."""

    @property
    @abstractmethod
    def serial_number(self) -> int | None:
        """None until the device has told it."""

    @property
    @abstractmethod
    def device_type(self) -> DeviceType | None:
        """None until the device family is known."""

    @property
    @abstractmethod
    def firmware_version(self) -> int | None:
        """None until the device has told it."""

    @property
    @abstractmethod
    def connection_type(self) -> ConnectionType:
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @property
    @abstractmethod
    def sample_rate_hz(self) -> float | None:
        """Data points per second; 0 when the output is off, None when the
        device paces itself (P2 Pro size distribution mode)."""

    @abstractmethod
    def write(self, command: str) -> None:
        """Send a command that has no answer, for example "X0001!".

        Raises:
            ConnectionError: the device is not connected.
        """

    @abstractmethod
    def query(self, command: str, timeout: float | None = None) -> list[str]:
        """Send a command and return the tab separated fields of its answer.

        One command is in flight per device; calls from several threads queue up.

        Raises:
            ConnectionError: the device is not connected.
            TimeoutError: no answer within timeout (default: what suits the transport).
        """

    @abstractmethod
    def set_sample_rate(self, hz: int | None) -> None:
        """Set the data rate to 0 (off), 1, 10 or 100 Hz, or None for the default
        of the device: 1 Hz, or the size distribution mode of a P2 Pro, where the
        device sets the pace itself.

        The upload to naneos is limited to 1 Hz whatever is set here.

        Raises:
            NotSupportedError: over BLE, where the rate is fixed at 1 Hz (None is fine).
            ValueError: for a rate the device does not offer.
        """

    @abstractmethod
    def read_ui_curve(self, timeout: float | None = None) -> UiCurve:
        """Sweep the corona voltage and read the resulting UI curve, 100 points.

        Blocks for the sweep (10 s) plus the readout, so 15 s or more. The
        measurement is disturbed by the sweep: the data points of the device
        are held back until it has settled again.

        Args:
            timeout: for the readout that follows the sweep; default 30 s.

        Raises:
            NotSupportedError: a P1, or firmware older than 418.
            TimeoutError: the curve did not arrive complete within the timeout.
            ConnectionError: the device is not connected.
        """

    @abstractmethod
    def read_pulse_form(self, timeout: float | None = None) -> PulseForm:
        """Read the form of the last charging pulse, 200 samples. Does not disturb
        the measurement.

        Args:
            timeout: for the readout; default 30 s.

        Raises:
            NotSupportedError: a P1, or firmware older than 418.
            TimeoutError: the form did not arrive complete within the timeout.
            ConnectionError: the device is not connected.
        """

    def __repr__(self) -> str:
        kind = self.device_type.name if self.device_type is not None else "?"
        return f"<{type(self).__name__} SN{self.serial_number} {kind} {self.connection_type}>"

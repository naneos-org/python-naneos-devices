from naneos.data_point import DeviceType
from naneos.device import NotSupportedError
from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_DATA_STRUCTURE,
    PARTECTOR2_PRO_DATA_STRUCTURE_V311,
    PARTECTOR2_PRO_DATA_STRUCTURE_V336,
)
from naneos.partector.blueprints._partector_blueprint import PartectorBlueprint
from naneos.partector.serial_transport import SerialTransport


class Partector2Pro(PartectorBlueprint):
    """The P2 Pro has two output modes.

    Size distribution (default): one line with the size distribution every few
    seconds, paced by the device; sample_rate_hz is None.
    P2 mode: the plain P2 line at 1, 10 or 100 Hz, without size distribution.
    """

    DEVICE_TYPE = DeviceType.P2PRO

    MIN_FIRMWARE_P2_MODE = 311

    def __init__(
        self,
        serial_number: int | None = None,
        port: str | None = None,
        size_distribution: bool = True,
        sample_rate_hz: int = 1,
        gain_test_active: bool = True,
        output_pulse_diagnostics: bool = True,
        transport: SerialTransport | None = None,
    ) -> None:
        """See PartectorBlueprint. sample_rate_hz only applies with size_distribution=False."""
        self._size_distribution = size_distribution
        self._want_gain_test = gain_test_active
        self._want_pulse_diagnostics = output_pulse_diagnostics
        super().__init__(serial_number, port, sample_rate_hz, transport)

    @property
    def size_distribution(self) -> bool:
        return self._size_distribution

    def set_size_distribution(self, active: bool, sample_rate_hz: int = 1) -> None:
        """Switch between the two output modes; sample_rate_hz is for the P2 mode.

        With the gain test active, every switch holds the data back until the
        device has settled again (see is_settling).
        """
        if active:
            self._enter_size_dist_mode()
        else:
            self._enter_p2_mode(sample_rate_hz)

    def set_sample_rate(self, hz: int) -> None:
        if self._size_distribution and hz != 0:
            raise NotSupportedError(
                "The size distribution mode has no selectable rate. "
                "Call set_size_distribution(False) first."
            )
        super().set_sample_rate(hz)

    def _configure(self) -> None:
        """Nothing to do here: a mode switch resets the device settings, so they
        are sent by _apply_settings() after every switch."""

    def _apply_settings(self) -> None:
        self.write("A0002!")  # activates antispikes
        self._configure_diagnostics(self._want_gain_test, self._want_pulse_diagnostics)

    def _start_output(self, sample_rate_hz: int) -> None:
        self.set_size_distribution(self._size_distribution, sample_rate_hz)

    def _enter_p2_mode(self, hz: int) -> None:
        if self._fw < self.MIN_FIRMWARE_P2_MODE:
            raise NotSupportedError(
                f"The P2 mode needs firmware {self.MIN_FIRMWARE_P2_MODE} or newer."
            )
        if hz not in self.SAMPLE_RATE_CODES:
            raise ValueError(f"Sample rate must be one of {sorted(self.SAMPLE_RATE_CODES)} Hz.")

        self.write("M0000!")  # deactivates size dist mode
        self._apply_settings()
        self._data_structure = {**PARTECTOR2_DATA_STRUCTURE, **self._diagnostic_columns()}
        self._size_distribution = False
        super().set_sample_rate(hz)

    def _enter_size_dist_mode(self) -> None:
        base = (
            PARTECTOR2_PRO_DATA_STRUCTURE_V336
            if self._fw >= 336
            else PARTECTOR2_PRO_DATA_STRUCTURE_V311
        )
        self.write("X0006!")  # verbose output of the size dist mode
        self.write("M0004!")  # activates size dist mode
        self._apply_settings()
        self._data_structure = {**base, **self._diagnostic_columns()}
        self._size_distribution = True
        self._sample_rate_hz = None  # paced by the device

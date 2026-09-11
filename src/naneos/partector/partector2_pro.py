from naneos.data_point import DeviceType
from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_DATA_STRUCTURE,
    PARTECTOR2_PRO_DATA_STRUCTURE_V311,
    PARTECTOR2_PRO_DATA_STRUCTURE_V336,
)
from naneos.partector.blueprints._partector_blueprint import PartectorBlueprint


class Partector2Pro(PartectorBlueprint):
    def __init__(
        self,
        serial_number: int | None = None,
        port: str | None = None,
        verb_freq: int = 6,
        gain_test_active: bool = True,
        output_pulse_diagnostics: bool = True,
    ) -> None:
        self._GAIN_TEST_ACTIVE = gain_test_active
        self._OUTPUT_PULSE_DIAGNOSTICS = output_pulse_diagnostics
        super().__init__(serial_number, port, verb_freq, DeviceType.P2PRO)

    def _init_serial_data_structure(self) -> None:
        """The structure depends on the mode and is selected in _set_verbose_freq."""

    def _set_verbose_freq(self, freq: int) -> None:
        """Selects the output mode: 0 off, 1-3 plain P2 line at that rate, 6 size distribution."""
        if freq == 0:
            self._write_line("X0000!")
        elif freq in [1, 2, 3]:
            self._enter_p2_mode(freq)
        elif freq == 6:
            self._enter_size_dist_mode()
        else:
            raise ValueError("Frequency must be 0, 1, 2, 3 or 6!")

    def _enter_p2_mode(self, freq: int) -> None:
        """Plain P2 line without size distribution."""
        if self._fw < 311:
            raise RuntimeError("Firmware too old for P2 pro mode. Minimum FW is 311.")

        # Copy: the diagnostics columns are added per instance and must not
        # leak into the module-level layout shared by other devices.
        self._data_structure = dict(PARTECTOR2_DATA_STRUCTURE)

        self._write_line("M0000!")  # deactivates size dist mode
        self._write_line("A0002!")  # activates antispikes
        self._configure_diagnostics(self._GAIN_TEST_ACTIVE, self._OUTPUT_PULSE_DIAGNOSTICS)
        self._write_line(f"X000{freq}!")  # set verbose freq

    def _enter_size_dist_mode(self) -> None:
        """The P2 Pro line with the size distribution, at the device's own rate."""
        if self._fw >= 336:
            self._data_structure = dict(PARTECTOR2_PRO_DATA_STRUCTURE_V336)
        else:
            self._data_structure = dict(PARTECTOR2_PRO_DATA_STRUCTURE_V311)

        self._write_line("X0006!")  # activates verbose mode
        self._write_line("M0004!")  # activates size dist mode
        self._write_line("A0002!")  # activates the antispikes
        self._configure_diagnostics(self._GAIN_TEST_ACTIVE, self._OUTPUT_PULSE_DIAGNOSTICS)

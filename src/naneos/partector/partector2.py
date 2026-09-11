from naneos.data_point import DeviceType
from naneos.logger import get_naneos_logger
from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_DATA_STRUCTURE,
    PARTECTOR2_DATA_STRUCTURE_V265_V275,
)
from naneos.partector.blueprints._partector_blueprint import PartectorBlueprint

logger = get_naneos_logger(__name__)


class Partector2(PartectorBlueprint):
    def __init__(
        self,
        serial_number: int | None = None,
        port: str | None = None,
        verb_freq: int = 1,
        gain_test_active: bool = True,
        output_pulse_diagnostics: bool = True,
    ) -> None:
        self._GAIN_TEST_ACTIVE = gain_test_active
        self._OUTPUT_PULSE_DIAGNOSTICS = output_pulse_diagnostics
        super().__init__(serial_number, port, verb_freq, DeviceType.P2)

    def _init_serial_data_structure(self) -> None:
        # Copies: the optional diagnostics columns are added per instance and
        # must not leak into the module-level layouts shared by other devices.
        if self._fw in [265, 275]:
            self._data_structure = dict(PARTECTOR2_DATA_STRUCTURE_V265_V275)
            logger.info(f"SN{self._sn} has FW{self._fw}. -> Using V265/275 data structure.")
            logger.info("Contact naneos for a firmware update to get the latest features.")
        elif self._fw in [295, 297, 298]:
            self._data_structure = dict(PARTECTOR2_DATA_STRUCTURE)
            logger.info(f"SN{self._sn} has FW{self._fw}. -> Using V295/297/298 data structure.")
            logger.info("Contact naneos for a firmware update to get the latest features.")
        elif self._fw >= 320:
            self._data_structure = dict(PARTECTOR2_DATA_STRUCTURE)
            self._write_line("A0002!")  # activates antispikes
            self._configure_diagnostics(self._GAIN_TEST_ACTIVE, self._OUTPUT_PULSE_DIAGNOSTICS)
            logger.info(f"SN{self._sn} has FW{self._fw}. -> Using V320 data structure.")
        else:
            self._data_structure = dict(PARTECTOR2_DATA_STRUCTURE)
            self._legacy_data_structure = True
            logger.warning(f"SN{self._sn} has FW{self._fw}. -> Unofficial firmware version.")
            logger.warning("Using legacy data structure. Contact naneos for a FW update.")

    def _set_verbose_freq(self, freq: int) -> None:
        """
        Set the frequency of the verbose output.

        :param int freq: Frequency of the verbose output in Hz. (0: off, 1: 1Hz, 2: 10Hz, 3: 100Hz)
        """

        if freq < 0 or freq > 3:
            raise ValueError("Frequency must be between 0 and 3!")

        self._write_line(f"X000{freq}!")

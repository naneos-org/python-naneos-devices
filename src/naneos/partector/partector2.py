from naneos.data_point import DeviceType
from naneos.logger import get_naneos_logger
from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_DATA_STRUCTURE,
    PARTECTOR2_DATA_STRUCTURE_V265_V275,
)
from naneos.partector.blueprints._partector_blueprint import PartectorBlueprint
from naneos.partector.serial_transport import SerialTransport

logger = get_naneos_logger(__name__)


class Partector2(PartectorBlueprint):
    DEVICE_TYPE = DeviceType.P2

    def __init__(
        self,
        serial_number: int | None = None,
        port: str | None = None,
        sample_rate_hz: int = 1,
        gain_test_active: bool = True,
        output_pulse_diagnostics: bool = True,
        transport: SerialTransport | None = None,
    ) -> None:
        """See PartectorBlueprint. The two diagnostics need firmware 320 or newer."""
        self._want_gain_test = gain_test_active
        self._want_pulse_diagnostics = output_pulse_diagnostics
        super().__init__(serial_number, port, sample_rate_hz, transport)

    def _configure(self) -> None:
        if self._fw in [265, 275]:
            self._data_structure = dict(PARTECTOR2_DATA_STRUCTURE_V265_V275)
            self._log_old_firmware("V265/275")
        elif self._fw in [295, 297, 298]:
            self._data_structure = dict(PARTECTOR2_DATA_STRUCTURE)
            self._log_old_firmware("V295/297/298")
        elif self._fw >= 320:
            self.write("A0002!")  # activates antispikes
            self._configure_diagnostics(self._want_gain_test, self._want_pulse_diagnostics)
            self._data_structure = {**PARTECTOR2_DATA_STRUCTURE, **self._diagnostic_columns()}
        else:
            self._data_structure = dict(PARTECTOR2_DATA_STRUCTURE)
            self._legacy_data_structure = True
            logger.warning(f"SN{self._sn} has FW{self._fw}. -> Unofficial firmware version.")
            logger.warning("Using legacy data structure. Contact naneos for a FW update.")

    def _log_old_firmware(self, layout: str) -> None:
        logger.info(f"SN{self._sn} has FW{self._fw}. -> Using {layout} data structure.")
        logger.info("Contact naneos for a firmware update to get the latest features.")

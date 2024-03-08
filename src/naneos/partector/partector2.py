from typing import Optional

from naneos.logger import get_naneos_logger
from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_DATA_STRUCTURE_V299,
    PARTECTOR2_DATA_STRUCTURE_V_LEGACY,
)
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint

logger = get_naneos_logger(__name__)


class Partector2(PartectorBluePrint):
    def __init__(
        self, serial_number: Optional[int] = None, port: Optional[str] = None, verb_freq: int = 1
    ) -> None:
        super().__init__(serial_number, port, verb_freq, "P2")

    def _init_serial_data_structure(self) -> None:
        if self._fw > 298:
            self._data_structure = PARTECTOR2_DATA_STRUCTURE_V299
            logger.info(f"SN{self._sn} has FW{self._fw}. -> Using V299 data structure.")
        else:
            self._data_structure = PARTECTOR2_DATA_STRUCTURE_V_LEGACY
            logger.info(f"SN{self._sn} has FW{self._fw}. -> Using legacy data structure.")

    def _set_verbose_freq(self, freq: int) -> None:
        """
        Set the frequency of the verbose output.

        :param int freq: Frequency of the verbose output in Hz. (0: off, 1: 1Hz, 2: 10Hz, 3: 100Hz)
        """

        if freq < 0 or freq > 3:
            raise ValueError("Frequency must be between 0 and 3!")

        self._write_line(f"X000{freq}!")


if __name__ == "__main__":
    import time

    from naneos.partector import scan_for_serial_partectors

    # production scanning:
    p2 = Partector2(serial_number=8112)
    time.sleep(5)
    print(p2.get_data_pandas())
    p2.close()

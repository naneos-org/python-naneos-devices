from typing import Optional

import pandas as pd

from naneos.logger import get_naneos_logger
from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_DATA_STRUCTURE_LEGACY,
    PARTECTOR2_DATA_STRUCTURE_V265_V275,
    PARTECTOR2_DATA_STRUCTURE_V295_V297_V298,
    PARTECTOR2_DATA_STRUCTURE_V320,
    NaneosDeviceDataPoint,
)
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint

logger = get_naneos_logger(__name__)


class Partector2(PartectorBluePrint):
    def __init__(
        self, serial_number: Optional[int] = None, port: Optional[str] = None, verb_freq: int = 1
    ) -> None:
        super().__init__(serial_number, port, verb_freq, "P2")

    def _init_serial_data_structure(self) -> None:
        self.device_type = NaneosDeviceDataPoint.DEV_TYPE_P2

        if self._fw in [265, 275]:
            self._data_structure = PARTECTOR2_DATA_STRUCTURE_V265_V275
            logger.info(f"SN{self._sn} has FW{self._fw}. -> Using V265/275 data structure.")
            logger.info("Contact naneos for a firmware update to get the latest features.")
        elif self._fw in [295, 297, 298]:
            self._data_structure = PARTECTOR2_DATA_STRUCTURE_V295_V297_V298
            logger.info(f"SN{self._sn} has FW{self._fw}. -> Using V295/297/298 data structure.")
            logger.info("Contact naneos for a firmware update to get the latest features.")
        elif self._fw >= 320:
            self._data_structure = PARTECTOR2_DATA_STRUCTURE_V320
            self._write_line("h2001!")  # activates harmonics output
            logger.info(f"SN{self._sn} has FW{self._fw}. -> Using V320 data structure.")
        else:
            self._data_structure = PARTECTOR2_DATA_STRUCTURE_LEGACY
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


if __name__ == "__main__":
    import time

    from naneos.partector.scanPartector import scan_for_serial_partectors

    partectors = scan_for_serial_partectors()
    assert partectors["P2"], "No Partector found!"
    serial_number, port = next(iter(partectors["P2"].items()))

    data: dict[int, pd.DataFrame] = {}
    p2 = Partector2(port=port)

    for _ in range(15):
        time.sleep(5)
        data_points = p2.get_data()
        for point in data_points:
            data = NaneosDeviceDataPoint.add_data_point_to_dict(data, point)

        df = next(iter(data.values()), pd.DataFrame())
        if not df.empty:
            print(f"Sn: {p2._sn}, Port: {p2._port}")
            print(df)
            data = {}
            # break

    p2.close(blocking=True)

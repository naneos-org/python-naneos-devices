from typing import Optional

import pandas as pd

from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_DATA_STRUCTURE_V320,
    PARTECTOR2_PRO_DATA_STRUCTURE_V311,
    PARTECTOR2_PRO_DATA_STRUCTURE_V336,
    NaneosDeviceDataPoint,
)
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint


class Partector2Pro(PartectorBluePrint):
    def __init__(
        self,
        serial_number: Optional[int] = None,
        port: Optional[str] = None,
        verb_freq: int = 6,
        hw_version: str = "P2pro",
    ) -> None:
        super().__init__(serial_number, port, verb_freq, hw_version)

    def _init_serial_data_structure(self) -> None:
        """This gets passed here and is set in the set_verbose_freq method."""
        self.device_type = NaneosDeviceDataPoint.DEV_TYPE_P2PRO

    def _set_verbose_freq(self, freq: int) -> None:
        if freq == 0:
            self._write_line("X0000!")
        elif freq in [1, 2, 3]:  # std p2 mode
            if self._fw >= 311:
                self._data_structure = PARTECTOR2_DATA_STRUCTURE_V320

            self._write_line("h2001!")  # activates harmonics output
            self._write_line("M0000!")  # deactivates size dist mode
            self._write_line(f"X000{freq}!")
        elif freq == 6:  # p2 pro mode
            if self._fw >= 336:
                self._data_structure = PARTECTOR2_PRO_DATA_STRUCTURE_V336
            else:
                self._data_structure = PARTECTOR2_PRO_DATA_STRUCTURE_V311

            self._write_line("X0006!")  # activates verbose mode
            self._write_line("h2001!")  # activates harmonics output
            self._write_line("M0004!")  # activates size dist mode
            self._write_line("A0001!")  # activates the antispikes


if __name__ == "__main__":
    import time

    from naneos.partector.scanPartector import scan_for_serial_partectors

    partectors = scan_for_serial_partectors()
    assert partectors["P2pro"], "No Partector found!"
    serial_number, port = next(iter(partectors["P2pro"].items()))

    data: dict[int, pd.DataFrame] = {}
    p2_pro = Partector2Pro(port=port)

    for _ in range(5):
        time.sleep(5)
        data_points = p2_pro.get_data()
        for point in data_points:
            data = NaneosDeviceDataPoint.add_data_point_to_dict(data, point)

        df = next(iter(data.values()), pd.DataFrame())
        if not df.empty:
            print(f"Sn: {p2_pro._sn}, Port: {p2_pro._port}")
            print(df)
            break

        print("No data received yet...")

    p2_pro.close(blocking=True)

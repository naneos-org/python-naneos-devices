from typing import Optional

import pandas as pd

from naneos.partector.blueprints._data_structure import (
    PARTECTOR1_DATA_STRUCTURE_V_LEGACY,
    NaneosDeviceDataPoint,
)
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint


class Partector1(PartectorBluePrint):
    def __init__(
        self, serial_number: Optional[int] = None, port: Optional[str] = None, verb_freq: int = 1
    ) -> None:
        super().__init__(serial_number, port, verb_freq)

    def _init_serial_data_structure(self) -> None:
        self.device_type = NaneosDeviceDataPoint.DEV_TYPE_P1
        self._data_structure = PARTECTOR1_DATA_STRUCTURE_V_LEGACY
        self._legacy_data_structure = True

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
    assert partectors["P1"], "No Partector found!"
    serial_number, port = next(iter(partectors["P1"].items()))

    data: dict[int, pd.DataFrame] = {}
    p1 = Partector1(port=port)

    for _ in range(5):
        time.sleep(5)
        data_points = p1.get_data()
        for point in data_points:
            data = NaneosDeviceDataPoint.add_data_point_to_dict(data, point)

        df = next(iter(data.values()), pd.DataFrame())
        if not df.empty:
            print(f"Sn: {p1._sn}, Port: {p1._port}")
            print(df)
            break

        print("No data received yet...")

    p1.close(blocking=True)

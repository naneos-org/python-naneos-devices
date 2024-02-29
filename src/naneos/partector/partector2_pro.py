from typing import Optional

from naneos.partector.blueprints._data_structure import PARTECTOR2_PRO_DATA_STRUCTURE_V311
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint


class Partector2Pro(PartectorBluePrint):
    def __init__(
        self,
        serial_number: Optional[int] = None,
        port: Optional[str] = None,
        verb_freq: int = 1,
        hw_version: str = "P2_pro",
    ) -> None:
        super().__init__(serial_number, port, verb_freq, hw_version)

    def _init_serial_data_structure(self) -> None:
        self._data_structure = PARTECTOR2_PRO_DATA_STRUCTURE_V311

    def _set_verbose_freq(self, freq: int) -> None:
        if freq == 0:
            self._write_line("X0000!")
        else:
            self._write_line("M0004!")  # activates size dist mode
            self._write_line("X0006!")  # activates verbose mode


if __name__ == "__main__":
    import time

    from naneos.partector import scan_for_serial_partectors

    partectors = scan_for_serial_partectors()
    partectors = partectors["P2_Pro"]

    if not partectors:
        print("No Partector found!")
        exit()

    serial_number = next(iter(partectors.keys()))

    p2 = Partector2Pro(serial_number=serial_number)

    # print(p2.write_line("M?", 1))
    time.sleep(5)
    df = p2.get_data_pandas()
    print(df)
    # df.to_pickle("/Users/huegi/gitlocal/naneos/naneos-devices/tests/p2_pro_test_data.pkl")
    p2.close()

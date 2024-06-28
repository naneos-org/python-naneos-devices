from typing import Optional

from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_DATA_STRUCTURE_V320,
    PARTECTOR2_PRO_DATA_STRUCTURE_V311,
    PARTECTOR2_PRO_DATA_STRUCTURE_V336,
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
        # TODO: My idea is to remove that completely and set the data structure in the set_verbose_freq method for all devices
        pass

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

            self._write_line("h2001!")  # activates harmonics output
            self._write_line("M0004!")  # activates size dist mode
            self._write_line("X0006!")  # activates verbose mode


if __name__ == "__main__":
    import time

    from naneos.partector import scan_for_serial_partectors

    partectors = scan_for_serial_partectors()
    p2_pro = partectors["P2pro"]

    assert p2_pro, "No Partector found!"

    serial_number = next(iter(p2_pro.keys()))

    p2 = Partector2Pro(serial_number=serial_number, verb_freq=6)
    time.sleep(30)

    df = p2.get_data_pandas()
    print(df)
    # df.to_pickle("p2_pro.pkl")

    # for _ in range(10):
    #     time.sleep(5)
    #     print(p2.get_data_pandas())

    p2.close(verbose_reset=False, blocking=True)

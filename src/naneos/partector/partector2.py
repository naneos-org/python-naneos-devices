from typing import Optional

from naneos.partector.blueprints._data_structure import PARTECTOR2_DATA_STRUCTURE
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint


class Partector2(PartectorBluePrint):
    def __init__(
        self, serial_number: Optional[int] = None, port: Optional[str] = None, verb_freq: int = 1
    ) -> None:
        super().__init__(serial_number, port, verb_freq, "P2")

    def _init_serial_data_structure(self) -> None:
        self._data_structure = PARTECTOR2_DATA_STRUCTURE

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

    partectors = scan_for_serial_partectors()
    partectors = partectors["P2"]

    if not partectors:
        print("No Partector found!")
        exit()

    serial_number = next(iter(partectors.keys()))

    p2 = Partector2(serial_number=serial_number)

    print(p2.write_line("v?", 1))
    time.sleep(2)
    print(p2.get_data_pandas())
    p2.close()

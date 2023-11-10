from naneos.partector.blueprints._data_structure import PARTECTOR2_PRO_DATA_STRUCTURE
from naneos.partector.partector2_pro import Partector2Pro


class Partector2ProGarage(Partector2Pro):
    def __init__(self, port: str, verb_freq: int = 1) -> None:
        super().__init__(port, verb_freq)

    def set_verbose_freq(self, freq: int):
        if freq == 0:
            self._write_line("X0000!")
        else:
            self._write_line("X0006!")


if __name__ == "__main__":
    import time

    p2 = Partector2ProGarage("/dev/tty.usbmodemDOSEMet_1")

    print(p2.write_line("v?", 1))
    time.sleep(2)
    print(p2.get_data_pandas()["T"])
    p2.close()

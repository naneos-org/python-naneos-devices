from naneos.partector.blueprints._data_structure import PARTECTOR2_DATA_STRUCTURE
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint


class Partector2(PartectorBluePrint):
    def __init__(self, serial_number: int = None, port: str = None, verb_freq: int = 1):
        super().__init__(serial_number, port, verb_freq)

    def _init_serial_data_structure(self):
        self._data_structure = PARTECTOR2_DATA_STRUCTURE

    def _set_verbose_freq(self, freq: int):
        """
        Set the frequency of the verbose output.

        :param int freq: Frequency of the verbose output in Hz. (0: off, 1: 1Hz, 2: 10Hz, 3: 100Hz)
        """

        if freq < 0 or freq > 3:
            raise ValueError("Frequency must be between 0 and 3!")

        self._write_line(f"X000{freq}!")

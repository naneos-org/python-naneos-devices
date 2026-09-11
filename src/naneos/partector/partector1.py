from naneos.data_point import DeviceType
from naneos.partector.blueprints._data_structure import (
    PARTECTOR1_DATA_STRUCTURE_V_LEGACY,
)
from naneos.partector.blueprints._partector_blueprint import PartectorBlueprint


class Partector1(PartectorBlueprint):
    def __init__(
        self, serial_number: int | None = None, port: str | None = None, verb_freq: int = 1
    ) -> None:
        super().__init__(serial_number, port, verb_freq, DeviceType.P1)

    def _init_serial_data_structure(self) -> None:
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

import time
from typing import Optional

import pandas as pd

from naneos.logger import LEVEL_WARNING, get_naneos_logger
from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_DATA_STRUCTURE_LEGACY,
    PARTECTOR2_DATA_STRUCTURE_V265_V275,
    PARTECTOR2_DATA_STRUCTURE_V295_V297_V298,
    PARTECTOR2_DATA_STRUCTURE_V320,
    PARTECTOR2_GAIN_TEST_ADDITIONAL_DATA_STRUCTURE,
    PARTECTOR2_OUTPUT_PULSE_DIAGNOSTIC_ADDITIONAL_DATA_STRUCTURE,
    NaneosDeviceDataPoint,
)
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint

logger = get_naneos_logger(__name__, LEVEL_WARNING)


class Partector2(PartectorBluePrint):
    def __init__(
        self,
        serial_number: Optional[int] = None,
        port: Optional[str] = None,
        verb_freq: int = 1,
        gain_test_active: bool = True,
        output_pulse_diagnostics: bool = True,
    ) -> None:
        self._GAIN_TEST_ACTIVE = gain_test_active
        self._OUTPUT_PULSE_DIAGNOSTICS = output_pulse_diagnostics
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
            self._write_line("A0002!")  # activates antispikes

            if self._OUTPUT_PULSE_DIAGNOSTICS:
                self._write_line("opd01!")
                self._data_structure.update(
                    PARTECTOR2_OUTPUT_PULSE_DIAGNOSTIC_ADDITIONAL_DATA_STRUCTURE
                )
            else:
                self._write_line("opd00!")

            if self._GAIN_TEST_ACTIVE:
                waiting_time = max(10, (self._integration_time + 5))
                self._wait_with_data_output_until = time.time() + waiting_time
                self._write_line("h2001!")  # activates harmonics output
                self._write_line("e1100!")  # strength of gain test signal
                self._data_structure.update(PARTECTOR2_GAIN_TEST_ADDITIONAL_DATA_STRUCTURE)
            else:
                self._write_line("h2000!")  # deactivates harmonics output
                self._write_line("e0000!")  # deactivates gain test signal

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
    from naneos.partector.scanPartector import scan_for_serial_partectors

    partectors = scan_for_serial_partectors()
    assert partectors["P2"], "No Partector found!"
    serial_number, port = next(iter(partectors["P2"].items()))

    data: dict[int, pd.DataFrame] = {}
    p2 = Partector2(port=port, gain_test_active=True)

    for _ in range(5):
        time.sleep(3)
        data_points = p2.get_data()
        for point in data_points:
            data = NaneosDeviceDataPoint.add_data_point_to_dict(data, point)

        df = next(iter(data.values()), pd.DataFrame())
        if not df.empty:
            print(f"Sn: {p2._sn}, Port: {p2._port}")
            print(df)
            print(df["diffusion_current_delay_off"])
            data = {}
            # break

    p2.close(blocking=True)

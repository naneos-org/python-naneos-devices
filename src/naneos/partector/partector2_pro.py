import time
from typing import Optional

import pandas as pd

from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_DATA_STRUCTURE_V320,
    PARTECTOR2_GAIN_TEST_ADDITIONAL_DATA_STRUCTURE,
    PARTECTOR2_OUTPUT_PULSE_DIAGNOSTIC_ADDITIONAL_DATA_STRUCTURE,
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
        gain_test_active: bool = True,
        output_pulse_diagnostics: bool = True,
    ) -> None:
        self._GAIN_TEST_ACTIVE = gain_test_active
        self._OUTPUT_PULSE_DIAGNOSTICS = output_pulse_diagnostics
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

                self._write_line("M0000!")  # deactivates size dist mode
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

                self._write_line(f"X000{freq}!")  # set verbose freq

            else:
                raise RuntimeError("Firmware too old for P2 pro mode. Minimum FW is 311.")
        elif freq == 6:  # p2 pro mode
            if self._fw >= 336:
                self._data_structure = PARTECTOR2_PRO_DATA_STRUCTURE_V336
            else:
                self._data_structure = PARTECTOR2_PRO_DATA_STRUCTURE_V311

            self._write_line("X0006!")  # activates verbose mode
            self._write_line("M0004!")  # activates size dist mode
            self._write_line("A0002!")  # activates the antispikes

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


if __name__ == "__main__":
    from naneos.partector.scanPartector import scan_for_serial_partectors

    partectors = scan_for_serial_partectors()
    assert partectors["P2pro"], "No Partector found!"
    serial_number, port = next(iter(partectors["P2pro"].items()))

    data: dict[int, pd.DataFrame] = {}
    p2_pro = Partector2Pro(port=port, verb_freq=6, gain_test_active=True)

    for _ in range(5):
        time.sleep(3)
        data_points = p2_pro.get_data()
        for point in data_points:
            data = NaneosDeviceDataPoint.add_data_point_to_dict(data, point)

        df = next(iter(data.values()), pd.DataFrame())
        if not df.empty:
            print(f"Sn: {p2_pro._sn}, Port: {p2_pro._port}")
            print(df.dropna(axis=1, how="all"))
            # print(df["diffusion_current_delay_on"])
            break

        print("No data received yet...")

    p2_pro.close(blocking=True)

from datetime import datetime, timezone
from typing import Any, Optional

from naneos.logger.custom_logger import get_naneos_logger
from naneos.partector.blueprints._data_structure import (
    PARTECTOR2_PRO_CS_DATA_STRUCTURE_V315,
    NaneosDeviceDataPoint,
)
from naneos.partector.partector2_pro import Partector2Pro

logger = get_naneos_logger(__name__)


class Partector2ProCs(Partector2Pro):
    CS_OFF = 0
    CS_ON = 1
    CS_UNKNOWN = -1

    def __init__(
        self,
        serial_number: Optional[int] = None,
        port: Optional[str] = None,
        verb_freq: int = 1,
        **kwargs: Any,
    ) -> None:
        self._catalyst_state = self.CS_UNKNOWN
        self._auto_mode = True

        self._callback_catalyst = kwargs.get("callback_catalyst", None)
        if self._callback_catalyst is None:
            logger.error("No callback function for catalyst state given!")
            raise ValueError("No callback function for catalyst state given!")
        super().__init__(serial_number, port, verb_freq, "P2proCS")

    def _init_serial_data_structure(self) -> None:
        self.device_type = NaneosDeviceDataPoint.DEV_TYPE_P2PRO_CS
        self._data_structure = PARTECTOR2_PRO_CS_DATA_STRUCTURE_V315

    def _set_verbose_freq(self, freq: int) -> None:
        if freq == 0:
            self._write_line("X0000!")
        else:
            if self._fw >= 311:
                self._data_structure = PARTECTOR2_PRO_CS_DATA_STRUCTURE_V315

            self._write_line("h2001!")  # activates harmonics output
            self._write_line("M0004!")  # activates size dist mode
            self._write_line("X0006!")  # activates verbose mode

    def set_catalyst_state(self, state: str) -> None:
        """Sets the catalyst state to on, off or auto."""
        if not self._connected:
            return

        if state == "on":
            self._write_line("CSon!")
            self._cs_state = self.CS_ON
            self._auto_mode = False
        elif state == "off":
            self._write_line("CSoff!")
            self._cs_state = self.CS_OFF
            self._auto_mode = False
        elif state == "auto":
            self._write_line("CSauto!")
            self._auto_mode = True
        else:
            logger.warning(f"Unknown catalyst state: {state} -> nothing done.")
            return

        logger.info(f"Catalyst state set to {state}.")

    def _serial_reading_routine(self) -> None:
        line = self._read_line()

        if not line or line == "":
            return

        if "CS_on" in line:
            self._catalyst_state = self.CS_ON
            if self._callback_catalyst:
                self._callback_catalyst(True)
            self._mark_cs_change()
            return
        elif "CS_off" in line:
            self._catalyst_state = self.CS_OFF
            if self._callback_catalyst:
                self._callback_catalyst(False)
            self._mark_cs_change()
            return

        self._put_line_to_queue(line)

    def _mark_cs_change(self) -> None:
        try:
            last_line = self._queue.pop()
            last_line[-1] = f"1{last_line[-1]}"
            self._queue.append(last_line)
        except Exception as excep:
            logger.warning(f"Could not mark catalyst state change: {excep}")

    def _put_line_to_queue(self, line: str) -> None:
        unix_timestamp = int(datetime.now(tz=timezone.utc).timestamp())
        data = [unix_timestamp] + line.split("\t")

        self._notify_message_received()

        if len(data) != len(self._data_structure):
            self._queue_info.append(data)
            return

        state: Optional[int] = None
        try:
            state = int(data[-1])
        except Exception as excep:
            logger.warning(f"Could not parse catalyst state in backup function: {excep}")

        if state in [0, 1] and self._catalyst_state != state:
            if self._callback_catalyst:
                self._callback_catalyst(state == 1)
            self._catalyst_state = state
            logger.warning(f"Set catalyst state to {state} by backup function to.")

        self._queue.append(data)


if __name__ == "__main__":
    import time

    import pandas as pd

    def test_callback(state: bool) -> None:
        logger.info(f"Catalyst state changed to {state}.")

    logger.info("Starting...")

    p2 = Partector2ProCs(serial_number=8448, callback_catalyst=test_callback)

    start = time.time()
    df = pd.DataFrame()
    while time.time() - start < 30:
        data_points = p2.get_data()
        data: dict[int, pd.DataFrame] = {}
        for point in data_points:
            data = NaneosDeviceDataPoint.add_data_point_to_dict(data, point)
        df_tmp = next(iter(data.values()), pd.DataFrame())

        if len(df_tmp) > 0:
            df = pd.concat([df, df_tmp])
        time.sleep(0.01)

    print(df)
    # df.to_pickle("tests/df_garagae.pkl")

    print("Closing...")
    p2.close(blocking=True)
    print("Closed!")

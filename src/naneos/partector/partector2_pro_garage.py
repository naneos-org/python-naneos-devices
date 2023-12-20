from datetime import datetime, timezone
import stat
from typing import Any, Optional

from naneos.logger.custom_logger import get_naneos_logger
from naneos.partector.blueprints._data_structure import PARTECTOR2_PRO_GARAGE_DATA_STRUCTURE
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint

logger = get_naneos_logger(__name__)


class Partector2ProGarage(PartectorBluePrint):
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
        super().__init__(serial_number, port, verb_freq)

    def _init_serial_data_structure(self) -> None:
        self._data_structure = PARTECTOR2_PRO_GARAGE_DATA_STRUCTURE

    def _set_verbose_freq(self, freq: int) -> None:
        if freq == 0:
            self._write_line("X0000!")
        else:
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

        # check if line contains !CS_on or !CS_off and remove it from line
        if "!CS_on" in line:
            line = line.replace("!CS_on", "")
            self._callback_catalyst(True)
            self._put_line_to_queue(line, True)
            self._catalyst_state = self.CS_ON
        elif "!CS_off" in line:
            line = line.replace("!CS_off", "")
            self._callback_catalyst(False)
            self._put_line_to_queue(line, False)
            self._catalyst_state = self.CS_OFF
        else:
            self._put_line_to_queue(line)

    def _put_line_to_queue(self, line: str, cs_command: Optional[bool] = None) -> None:
        unix_timestamp = int(datetime.now(tz=timezone.utc).timestamp())
        data = [unix_timestamp] + line.split("\t")

        self._notify_message_received()

        if len(data) != len(self._data_structure):
            self._put_to_info_queue(data)
            return

        state: Optional[int] = None
        try:
            state = int(data[-1])
        except Exception as excep:
            logger.warning(f"Could not parse catalyst state in backup function: {excep}")

        if state in [0, 1] and self._catalyst_state != state:
            self._callback_catalyst(state == 1)
            self._catalyst_state = state
            logger.warning(f"Set catalyst state to by backup function to {state}.")

        # removes the size dist from all the measurements that are not wanted
        if cs_command is None and self._auto_mode:
            data[20:28] = [0] * 8

        self._put_to_data_queue(data)

    def _put_to_info_queue(self, data: list[int | str]) -> None:
        if self._queue_info.full():
            self._queue_info.get()
        self._queue_info.put(data)

    def _put_to_data_queue(self, data: list[int | str]) -> None:
        if self._queue.full():
            self._queue.get()
        self._queue.put(data)


if __name__ == "__main__":
    import time

    def test_callback(state: bool) -> None:
        logger.info(f"Catalyst state changed to {state}.")

    logger.info("Starting...")

    p2 = Partector2ProGarage(serial_number=8421, callback_catalyst=test_callback)

    # print(p2.write_line("v?", 1))
    time.sleep(5)

    df = p2.get_data_pandas()
    print(df)
    df.to_pickle("tests/df_garagae.pkl")

    print("Closing...")
    p2.close(blocking=True)
    print("Closed!")

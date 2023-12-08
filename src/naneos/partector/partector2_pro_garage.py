from datetime import datetime, timezone

from naneos.logger.custom_logger import get_naneos_logger
from naneos.partector.blueprints._data_structure import PARTECTOR2_PRO_GARAGE_DATA_STRUCTURE
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint

logger = get_naneos_logger(__name__)


class Partector2ProGarage(PartectorBluePrint):
    CS_OFF = 0
    CS_ON = 1
    CS_UNKNOWN = -1

    def __init__(self, serial_number: int = None, port: str = None, verb_freq: int = 1, **kwargs):
        self._catalyst_state = self.CS_UNKNOWN
        self._auto_mode = True

        self._callback_catalyst = kwargs.get("callback_catalyst", None)
        super().__init__(serial_number, port, verb_freq)

    def _get_and_check_info(self, expected_length: int = 3) -> list:
        return super()._get_and_check_info(expected_length)

    def _init_serial_data_structure(self):
        self._data_structure = PARTECTOR2_PRO_GARAGE_DATA_STRUCTURE

    def _set_verbose_freq(self, freq: int):
        if freq == 0:
            self._write_line("X0000!")
        else:
            self._write_line("X0006!")

    def set_catalyst_state(self, state: str):
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

    def _serial_reading_routine(self):
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

    def _put_line_to_queue(self, line: str, cs_command: bool = None):
        data = [datetime.now(tz=timezone.utc)] + line.split("\t")
        data = data + [self._catalyst_state]

        if len(data) != len(self._data_structure):
            self._put_to_info_queue(data)
            return

        # removes the size dist from all the measurements that are not wanted
        if cs_command is None and self._auto_mode:
            data[20:28] = [0] * 8

        self._put_to_data_queue(data)

    def _put_to_info_queue(self, data: list):
        if self._queue_info.full():
            self._queue_info.get()
        self._queue_info.put(data)

    def _put_to_data_queue(self, data: list):
        if self._queue.full():
            self._queue.get()
        self._queue.put(data)


if __name__ == "__main__":
    import time

    def test_callback(state: bool):
        print("Catalyst state: {}".format(state))

    p2 = Partector2ProGarage(test_callback, "/dev/tty.usbmodemDOSEMet_1")

    # print(p2.write_line("v?", 1))
    time.sleep(3)
    print(p2.get_data_pandas()["cs_status"])

    print("Closing...")
    p2.close(blocking=True)
    print("Closed!")

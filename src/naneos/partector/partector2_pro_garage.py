from datetime import datetime, timezone

from naneos.partector.blueprints._data_structure import PARTECTOR2_PRO_DATA_STRUCTURE
from naneos.partector.partector2_pro import Partector2Pro


class Partector2ProGarage(Partector2Pro):
    def __init__(self, callback_catalyst, port: str, verb_freq: int = 1) -> None:
        super().__init__(port, verb_freq)

        self._callback_catalyst = callback_catalyst

    def set_verbose_freq(self, freq: int):
        if freq == 0:
            self._write_line("X0000!")
        else:
            self._write_line("X0006!")

    def _serial_reading_routine(self):
        line = self._read_line()

        if not line or line == "":
            return

        # check if line contains !CS_on or !CS_off and remove it from line
        size_dist_received = False
        if "!CS_on" in line:
            self._callback_catalyst(True)
            line = line.replace("!CS_on", "")
            size_dist_received = True
        elif "!CS_off" in line:
            self._callback_catalyst(False)
            line = line.replace("!CS_off", "")
            size_dist_received = True

        data = [datetime.now(tz=timezone.utc)] + line.split("\t")

        if len(data) == len(self._data_structure):
            # set [-6] to [-13] to 0
            if not size_dist_received:
                data[20:28] = [0] * 8
                print(data)
            if self._queue.full():
                self._queue.get()
            self._queue.put(data)
        else:
            if self._queue_info.full():
                self._queue_info.get()
            self._queue_info.put(data)


if __name__ == "__main__":
    import time

    def test_callback(state: bool):
        print("Catalyst state: {}".format(state))

    p2 = Partector2ProGarage(test_callback, "/dev/tty.usbmodemDOSEMet_1")

    # print(p2.write_line("v?", 1))
    time.sleep(3)
    print(p2.get_data_pandas())

    print("Closing...")
    p2.close(blocking=True)
    print("Closed!")

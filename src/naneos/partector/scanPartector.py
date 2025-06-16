from queue import Queue
from threading import Thread
from typing import Any, Callable, Optional

from naneos.logger.custom_logger import get_naneos_logger
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint
from naneos.serial_utils import list_serial_ports

logger = get_naneos_logger(__name__)


class ScanPartector(PartectorBluePrint):
    def __init__(
        self,
        serial_number: Optional[int] = None,
        port: Optional[str] = None,
        verb_freq: int = 1,
    ) -> None:
        super().__init__(serial_number, port, verb_freq)

    def _init_print_connection_info(self) -> None:
        pass

    def _init_serial_data_structure(self) -> None:
        """This field is not used in the scan partector, but mandatory in the partector blueprint."""
        pass

    def _serial_wrapper(self, func: Callable[[], Any]) -> Optional[Any]:
        """Wraps user func in try-except block. Forwards exceptions to the user."""
        if not self._connected:
            return None

        excep = "Was not able to fetch the serial number!"

        for _ in range(self.SERIAL_RETRIES):
            try:
                return func()
            except Exception as e:
                # ßlogger.error(f"SN{self._sn} Exception in _serial_wrapper: {e}")
                excep = f"SN{self._sn} Exception occured during user function call: {e}"

        raise Exception(excep)

    def _init_get_device_info(self) -> None:
        try:
            if self._sn is None:
                self._sn = self._get_serial_number_secure()
            self._fw = self.get_firmware_version()
            logger.debug(f"Connected to SN{self._sn} on {self._port}")
        except Exception:
            # this gets just passed because scan partector scans every port
            # therefore it does not know if there is a partector
            pass

    def _set_verbose_freq(self, freq: int = 0) -> None:
        """This field is only used to set the verbose frequency to 0"""
        self._write_line("X0000!")


def scan_for_serial_partector(serial_number: int, partector_version: str) -> Optional[str]:
    """Scans all possible ports using threads (fast)."""
    threads = []
    q_1: Queue = Queue()
    q_2: Queue = Queue()
    q_2_pro: Queue = Queue()
    q_2_pro_cs: Queue = Queue()

    for port in list_serial_ports():
        threads.append(Thread(target=__scan_port, args=(port, q_1, q_2, q_2_pro, q_2_pro_cs)))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    q: Queue = Queue()
    if partector_version == "P1":
        q = q_1
    elif partector_version == "P2":
        q = q_2
    elif partector_version == "P2pro":
        q = q_2_pro
    elif partector_version == "P2proCS":
        q = q_2_pro_cs

    ports = {k: v for d in tuple(q.queue) for (k, v) in d.items()}
    logger.debug(f"Found ports: {ports}")

    if serial_number in ports:
        return ports[serial_number]

    return None


def scan_for_serial_partectors(ports_exclude: Optional[list] = None) -> dict:
    """Scans all possible ports using threads (fast)."""
    threads = []
    q_1: Queue = Queue()
    q_2: Queue = Queue()
    q_2_pro: Queue = Queue()
    q_2_pro_cs: Queue = Queue()

    if ports_exclude is None:
        ports_exclude = []

    for port in list_serial_ports(ports_exclude=ports_exclude):
        threads.append(Thread(target=__scan_port, args=(port, q_1, q_2, q_2_pro, q_2_pro_cs)))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    p1 = {k: v for x in tuple(q_1.queue) for (k, v) in x.items()}
    p2 = {k: v for x in tuple(q_2.queue) for (k, v) in x.items()}
    p2_pro = {k: v for x in tuple(q_2_pro.queue) for (k, v) in x.items()}
    p2_pro_cs = {k: v for x in tuple(q_2_pro_cs.queue) for (k, v) in x.items()}

    return {"P1": p1, "P2": p2, "P2pro": p2_pro, "P2proCS": p2_pro_cs}


def __scan_port(port: str, q_1: Queue, q_2: Queue, q_2_pro: Queue, q_2_pro_cs: Queue) -> None:
    try:
        partector = ScanPartector(port=port)

        if partector._sn is None:
            pass
        elif partector._sn < 1000:
            q_1.put({partector._sn: port})
        else:
            if partector._fw < 310:
                q_2.put({partector._sn: port})
            else:
                name: str = partector.write_line("name?")[1]
                if name == "P2":
                    q_2.put({partector._sn: port})
                elif name == "P2pro":
                    q_2_pro.put({partector._sn: port})
                elif name == "P2proCS":
                    q_2_pro_cs.put({partector._sn: port})

        partector.close(blocking=True)
    except Exception:
        if isinstance(partector, ScanPartector):
            partector.close(blocking=True)


if __name__ == "__main__":
    print(scan_for_serial_partectors())
    # print(scan_for_serial_partector(8617, "P2pro"))

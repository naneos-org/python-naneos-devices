from threading import Event, Thread

from logger.custom_logger import get_naneos_logger

# from naneos.partector import scan_for_serial_partectors
from naneos.partector.blueprints._partector_blueprint import PartectorBluePrint

logger = get_naneos_logger(__name__)


class AutoConnectingPartector(Thread):
    def __init__(self, serial_number: int, device_class: type, **kwargs):
        super().__init__()

        self.device: PartectorBluePrint = None

        self._stop_event = Event()

        self._serial_number = serial_number
        self._device_class = device_class
        self._kwargs = kwargs

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            try:
                while not self._stop_event.wait(0.9):
                    # connect to device if not found
                    if self.device is None:
                        port = self._search_for_device()
                        if port:
                            self.device = self._device_class(port, **self._kwargs)
                            print(f"Connected to device on port {port}")
                    else:
                        if self.device._check_device_connection():
                            print("Device is connected")
                        else:
                            self.device.close(blocking=True)
                            self.device = None
                            print("Device lost connection")
            except Exception as e:
                print(e)

        if self.device:
            self.device.close(blocking=True)
            self.device = None

    def _search_for_device(self):
        # ports = scan_for_serial_partectors()
        ports = [port for port in ports.values() if port]
        ports = {k: v for d in ports for k, v in d.items()}
        port = [v for d in ports for k, v in ports.items() if k == self._serial_number]

        if port:
            port = port[0]
            return port

        return None


if __name__ == "__main__":
    import time

    from naneos.partector import Partector2ProGarage

    partector = Partector2ProGarage(serial_number=8150)

    time.sleep(10)

    print(partector.get_data_pandas())
    partector.close(blocking=True)

    # logger.info("Starting auto connecting partector")

    # partectorAuto = AutoConnectingPartector(8150, Partector2ProGarage)
    # partectorAuto.start()
    # time.sleep(6)

    # partectorAuto.stop()

import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from queue import Queue
from threading import Event, Thread

import pandas
import serial

from logger.custom_logger import get_naneos_logger
from naneos.partector.blueprints._partector_defaults import PartectorDefaults
from naneos.partector.blueprints._partectorCheckerThread import PartectorCheckerThread

logger = get_naneos_logger(__name__)


class PartectorBluePrint(Thread, PartectorDefaults, ABC):
    """
    Class with the basic functionality of every Partector.
    Mandatory device specific methods are defined abstract and have to be implemented in the child class.
    """

    def __init__(self, serial_number: int = None, port: str = None, verb_freq: int = 1):
        """Initializes the Partector2 and starts the reading thread."""
        self._init(serial_number, port, verb_freq)

    def close(self, blocking: bool = False):
        """Closes the serial connection and stops the reading thread."""
        self._close(blocking)

    def run(self):
        """Thread method. Reads the serial port and puts the data into the queue."""
        checker_thread = PartectorCheckerThread(self)

        while not self.thread_event.is_set():
            self._run()

        checker_thread.stop()
        checker_thread.join()

        if self._ser.isOpen():
            self._ser.close()

    #########################################
    ### Abstract methods
    def set_verbose_freq(self, freq: int):
        """
        Sets the verbose frequency of the device.
        This differs for P1, P2 and P2Pro.
        """
        if not self._connected:
            return

        self._set_verbose_freq(freq)

    @abstractmethod
    def _set_verbose_freq(self, freq: int):
        """
        Sets the verbose frequency of the device.
        This differs for P1, P2 and P2Pro.
        """
        pass

    #########################################
    ### User accessible getters
    def get_serial_number(self) -> int:
        """Gets the serial number via command from the device."""
        return self._serial_wrapper(self._get_serial_number)

    def get_firmware_version(self) -> str:
        """Gets the firmware version via command from the device."""
        return self._serial_wrapper(self._get_firmware_version)

    def write_line(self, line: str, number_of_elem: int = 1) -> list:
        """
        Writes a custom line to the device.
        Returns the tab separated response as list.

        :param str line: The line to write to the device.
        :param int number_of_elem: The number of elements in the response. This will be checked!
        :return: The response as list.
        """

        self.custom_info_str = line
        self.custom_info_size = number_of_elem + 1

        return self._serial_wrapper(self._custom_info)

    #########################################
    ### User accessible data methods
    def clear_data_cache(self):
        """Clears the data cache."""
        self._queue.queue.clear()

    def get_data_list(self) -> list:
        """Returns the cache as list with timestamp as first element."""
        data_casted = []
        data = list(self._queue.queue)
        self.clear_data_cache()

        for line in data:
            try:
                data_casted.append(self._cast_splitted_input_string(line))
            except Exception as excep:
                logger.warning(f"Could not cast data: {excep}")
                logger.warning(f"Data: {line}")

        return data_casted

    def get_data_pandas(self, data=None) -> pandas.DataFrame:
        """Returns the cache as pandas DataFrame with timestamp as index."""
        if not data:
            data = self.get_data_list()

        columns = self._data_structure.keys()
        df = pandas.DataFrame(data, columns=columns).set_index("dateTime")
        return df

    #########################################
    ### Serial methods (private)
    def _close(self, blocking):
        try:
            self.set_verbose_freq(0)
        except Exception:
            pass
        self.thread_event.set()
        if blocking:
            self.join()

    def _run(self):
        if not self._connected:
            return

        try:
            if self._ser.isOpen():
                self._serial_reading_routine()
        except Exception as e:
            logger.warning(f"Exception occured during threaded serial reading: {e}")

    def _run_check_connection(self) -> bool:
        """Checks if the device is still connected."""
        if not self._connected:
            # try to reconnect
            self._init_serial(self._serial_number, self._port)
            self.set_verbose_freq(1)
            return

        if self._check_device_connection() is False:
            self._ser.close()
            self._connected = False

            logger.warning(f"Partector on port {self._port} disconnected!")
            self._port = None

    def _serial_reading_routine(self):
        if not self._connected:
            return

        line = self._read_line()

        if not line or line == "":
            return

        data = [datetime.now(tz=timezone.utc)] + line.split("\t")

        if len(data) == len(self._data_structure):
            if self._queue.full():
                self._queue.get()
            self._queue.put(data)
        else:
            if self._queue_info.full():
                self._queue_info.get()
            self._queue_info.put(data)

    def _check_device_connection(self) -> bool:
        if self.thread_event.is_set():
            return False
        elif not self._ser.isOpen():
            return False

        try:
            sn = self._get_serial_number_secure()
            if sn == self._serial_number:
                return True

        except Exception as e:
            logger.error(f"Exception occured during device connection check: {e}")

        return False

    def _check_serial_connection(self):
        """Tries to reopen a closed connection. Raises exceptions on failure."""
        try:
            for _ in range(3):
                self._ser.open() if not self._ser.isOpen() else None
                if self._ser.isOpen():
                    return None
        except Exception as e:
            self._ser.close()
            self._connected = False
            raise Exception(f"Was not able to open the Serial connection: {e}")

    def _serial_wrapper(self, func):
        """Wraps user func in try-except block. Forwards exceptions to the user."""
        if not self._connected:
            return

        for _ in range(self.SERIAL_RETRIES):
            try:
                return func()
            except Exception as e:
                logger.error(f"Exception in _serial_wrapper: {e}")
                excep = f"Exception occured during user function call: {e}"
        raise Exception(excep)

    def _write_line(self, line: str):
        if not self._connected:
            return

        self._check_serial_connection()
        self._ser.write(line.encode())

    def _read_line(self) -> str:
        if not self._connected:
            return

        self._check_serial_connection()
        try:
            data = self._ser.readline().decode()
        except Exception as e:
            self._ser.close()
            self._connected = False
            raise Exception(f"Was not able to read from the Serial connection: {e}")
        return data.replace("\r", "").replace("\n", "").replace("\x00", "")

    def _get_and_check_info(self, length: int = 2) -> list:
        data = self._queue_info.get(timeout=self.SERIAL_TIMEOUT_INFO)
        if len(data) != length:
            raise Exception(f"Info length {len(data)} not matching {length}: {data}")
        return data

    def _get_serial_number_secure(self) -> int:
        if not self._connected:
            return

        for _ in range(3):
            serial_numbers = [self.get_serial_number() for _ in range(3)]
            if all(x == serial_numbers[0] for x in serial_numbers):
                return serial_numbers[0]
        raise Exception("Was not able to fetch the serial number (secure)!")

    def _get_serial_number(self) -> int:
        self._queue_info.queue.clear()
        self._write_line("N?")
        return int(self._get_and_check_info()[1])

    def _get_firmware_version(self) -> str:
        self._queue_info.queue.clear()
        self._write_line("f?")
        return int(self._get_and_check_info()[1])

    def _custom_info(self) -> list:
        self._queue_info.queue.clear()
        self._write_line(self.custom_info_str)
        return self._get_and_check_info(self.custom_info_size)

    def _cast_splitted_input_string(self, line: str):
        for i, data_type in enumerate(self._data_structure.values()):
            if type(line[i]) is not data_type:
                line[i] = data_type(line[i])

        return line

    #########################################
    ### Init methods
    def _init(self, serial_number, port, verb_freq):
        self._init_serial(serial_number, port)
        self._init_thread()
        self._init_data_structures()
        self._init_serial_data_structure()

        self._init_clear_buffers()
        self.start()
        self._init_get_device_info()

        self.set_verbose_freq(verb_freq)

    def _init_serial(self, serial_number: int, port: str):
        from naneos.partector import scan_for_serial_partector

        self._serial_number = serial_number
        self._port = port

        if self._serial_number:
            self._port = scan_for_serial_partector(self._serial_number)
        elif self._port is None:
            raise Exception("No serial number or port given!")

        self._ser = None
        if self._port:
            self._ser = serial.Serial(
                port=self._port,
                baudrate=self.SERIAL_BAUDRATE,
                timeout=self.SERIAL_TIMEOUT,
            )

        self._connected = False
        if self._ser:
            if self._ser.isOpen():
                self._connected = True
                logger.info(f"Connected to SN{self._serial_number} on {self._port}")

        self.set_verbose_freq(0)

    def _init_thread(self):
        Thread.__init__(self)
        self.name = "naneos-partector-thread"
        self.thread_event = Event()

    def _init_data_structures(self):
        self.custom_info_str = "0"
        self.custom_info_size = 0
        self._data_structure = None  # will be declared in child class
        self._queue = Queue(maxsize=self.SERIAL_QUEUE_MAXSIZE)
        self._queue_info = Queue(maxsize=self.SERIAL_INFO_QUEUE_MAXSIZE)

    @abstractmethod
    def _init_serial_data_structure(self):
        pass

    def _init_clear_buffers(self):
        if not self._connected:
            return

        time.sleep(10e-3)
        self._ser.reset_input_buffer()

    def _init_get_device_info(self):
        try:
            if self._serial_number is None:
                self._serial_number = self._get_serial_number_secure()
            self._firmware_version = self.get_firmware_version()
            logger.debug(f"Connected to SN{self._serial_number} on {self._ser.port}")
        except Exception:
            logger.warning("Could not get device info!")
            # port = self._ser.port
            # self.close()
            # raise ConnectionError(f"No partector2 on port {port}.")


if __name__ == "__main__":
    import time

    from naneos.partector import Partector2ProGarage

    partector = Partector2ProGarage(serial_number=8150)

    time.sleep(30)

    print(partector.get_data_pandas())
    partector.close(blocking=True)

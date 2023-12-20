from abc import ABC, abstractmethod
import collections
from datetime import datetime, timezone
from queue import Queue
import stat
from threading import Event, Thread
import time
from typing import Any, Callable, Optional

import pandas
import serial

from naneos.logger.custom_logger import get_naneos_logger
from naneos.partector.blueprints._partector_defaults import PartectorDefaults

logger = get_naneos_logger(__name__)


class PartectorBluePrint(Thread, PartectorDefaults, ABC):
    """
    Class with the basic functionality of every Partector.
    Mandatory device specific methods are defined abstract and have to be implemented in the child class.
    """

    def __init__(
        self, serial_number: Optional[int] = None, port: Optional[str] = None, verb_freq: int = 1
    ) -> None:
        """Initializes the Partector2 and starts the reading thread."""
        self._init_variables()
        self._init(serial_number, port, verb_freq)

    def _init_variables(self) -> None:
        self._connected = False
        self._serial_number: Optional[int] = None
        self._port: Optional[str] = ""
        self._ser: Optional[serial.Serial] = None
        self._time_last_message_received = time.time()

    def close(self, blocking: bool = False, shutdown: bool = False) -> None:
        """Closes the serial connection and stops the reading thread."""
        self._close(blocking, shutdown)

    def _checker_thread(self) -> None:
        while not self.thread_event.wait(0.5):
            if time.time() - self._time_last_message_received > 5:
                try:
                    logger.info("Checking device connection...")
                    self._run_check_connection()
                    self._time_last_message_received = time.time()
                except Exception as e:
                    logger.error(e)

    def _notify_message_received(self) -> None:
        self._time_last_message_received = time.time()

    def run(self) -> None:
        """Thread method. Reads the serial port and puts the data into the queue."""

        # run _checker_thread in own thread
        checker_thread = Thread(target=self._checker_thread)
        checker_thread.start()

        while not self.thread_event.is_set():
            self._run()

        checker_thread.join()

        if self._shutdown_partector:
            self.write_line("off!", 0)

        if isinstance(self._ser, serial.Serial) and self._ser.is_open:
            self._ser.close()

    #########################################
    ### Abstract methods
    def set_verbose_freq(self, freq: int) -> None:
        """
        Sets the verbose frequency of the device.
        This differs for P1, P2 and P2Pro.
        """
        if not self._connected:
            return

        self._set_verbose_freq(freq)

    @abstractmethod
    def _set_verbose_freq(self, freq: int) -> None:
        """
        Sets the verbose frequency of the device.
        This differs for P1, P2 and P2Pro.
        """
        pass

    #########################################
    ### User accessible getters
    def get_serial_number(self) -> Optional[int]:
        """Gets the serial number via command from the device."""
        return self._serial_wrapper(self._get_serial_number)

    def get_firmware_version(self) -> Optional[str]:
        """Gets the firmware version via command from the device."""
        return self._serial_wrapper(self._get_firmware_version)

    def write_line(self, line: str, number_of_elem: int = 1) -> list[Any]:
        """
        Writes a custom line to the device and returns the tab-separated response as a list.

        Args:
            line (str): The line to write to the device.
            number_of_elem (int, optional): The number of elements in the response. This will be checked. Defaults to 1.

        Returns:
            list: The response as a list.
        """
        self.custom_info_str = line
        self.custom_info_size = number_of_elem + 1

        return self._serial_wrapper(self._custom_info)  # type: ignore

    #########################################
    ### User accessible data methods
    def clear_data_cache(self) -> None:
        """Clears the data cache."""
        self._queue.queue.clear()

    def get_data_list(self) -> list[list[int | float]]:
        """Returns the cache as list with timestamp as first element."""
        data_casted: list[list[int | float]] = []
        data = list(self._queue.queue)
        self.clear_data_cache()

        for line in data:
            try:
                data_casted.append(self._cast_splitted_input_string(line))
            except Exception as excep:
                logger.warning(f"Could not cast data: {excep}")
                logger.warning(f"Data: {line}")

        return data_casted

    def get_data_pandas(self, data: Optional[list[list[int | float]]] = None) -> pandas.DataFrame:
        """Returns the cache as pandas DataFrame with timestamp as index."""
        if not data:
            data = self.get_data_list()

        columns = list(self._data_structure.keys())
        df = pandas.DataFrame(data, columns=columns).set_index("unix_timestamp")
        df = df[~df.index.duplicated(keep="last")]
        return df

    #########################################
    ### Serial methods (private)
    def _close(self, blocking: bool, shutdown: bool) -> None:
        try:
            self.set_verbose_freq(0)
        except Exception:
            logger.warning("Could not set verbose frequency to 0!")
        self._shutdown_partector = shutdown
        self.thread_event.set()
        if blocking:
            self.join()

    def _run(self) -> None:
        if not self._connected:
            return

        try:
            if isinstance(self._ser, serial.Serial) and self._ser.is_open:
                self._serial_reading_routine()
        except Exception as e:
            logger.warning(f"Exception occured during threaded serial reading: {e}")

    def _run_check_connection(self) -> bool:
        """Checks if the device is still connected."""
        if not self._connected:
            self._init_serial(self._serial_number, self._port)
            self.set_verbose_freq(1)
        elif self._check_device_connection() is False:
            if isinstance(self._ser, serial.Serial) and self._ser.is_open:
                self._ser.close()
            self._connected = False
            logger.warning(f"Partector on port {self._port} disconnected!")
            self._port = None

        return self._connected

    def _serial_reading_routine(self) -> None:
        if not self._connected:
            return

        line = self._read_line()

        if not line or line == "":
            return

        unix_timestamp = int(datetime.now(tz=timezone.utc).timestamp())
        data = [unix_timestamp] + line.split("\t")

        self._notify_message_received()

        if len(data) == len(self._data_structure):
            if self._queue.full():
                self._queue.get()
            self._queue.put(data)
        else:
            if self._queue_info.full():
                self._queue_info.get()
            self._queue_info.put(data)

    def _check_device_connection(self) -> bool:
        if self.thread_event.is_set() or not self._ser or not self._ser.is_open:
            return False

        try:
            sn = self._get_serial_number_secure()
            if sn == self._serial_number:
                return True

        except Exception as e:
            logger.error(f"Exception occured during device connection check: {e}")

        return False

    def _check_serial_connection(self) -> None:
        """Tries to reopen a closed connection. Raises exceptions on failure."""
        try:
            for _ in range(3):
                if not self._ser:
                    self._init_serial(self._serial_number, self._port)
                elif not self._ser.is_open:
                    self._ser.open()

                if self._ser and self._ser.is_open:
                    return None
        except Exception as e:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._connected = False
            raise ConnectionAbortedError(f"Serial connection aborted: {e}")

    def _serial_wrapper(self, func: Callable[[], Any]) -> Optional[Any]:
        """Wraps user func in try-except block. Forwards exceptions to the user."""
        if not self._connected:
            return None

        excep = "Was not able to fetch the serial number!"

        for _ in range(self.SERIAL_RETRIES):
            try:
                return func()
            except Exception as e:
                logger.error(f"Exception in _serial_wrapper: {e}")
                excep = f"Exception occured during user function call: {e}"

        raise Exception(excep)

    def _write_line(self, line: str) -> None:
        if not self._connected:
            return

        self._check_serial_connection()
        if self._ser:
            self._ser.write(line.encode())

    def _read_line(self) -> str:
        if not self._connected:
            return ""

        self._check_serial_connection()
        try:
            data = ""
            if self._ser:
                data = self._ser.readline().decode()
        except Exception as e:
            if self._ser:
                self._ser.close()
            self._connected = False
            raise Exception(f"Was not able to read from the Serial connection: {e}")

        return data.replace("\r", "").replace("\n", "").replace("\x00", "")

    def _get_and_check_info(self, expected_length: int = 2) -> list[int | str]:
        """
        Get information from the queue and check its length.

        Parameters:
            expected_length (int): The expected length of the information.

        Returns:
            list: The information from the queue.

        Raises:
            ValueError: If the length of the information does not match the expected length.
        """
        info_data = self._queue_info.get(timeout=self.SERIAL_TIMEOUT_INFO)
        if len(info_data) != expected_length:
            error_msg = f"Received data of length {len(info_data)}, expected {expected_length}. Data: {info_data}"
            raise ValueError(error_msg)
        return info_data

    def _get_serial_number_secure(self) -> Optional[int]:
        if not self._connected:
            return None

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
        fw = self._get_and_check_info()[1]
        if isinstance(fw, str):
            return fw
        return "Unknown"

    def _custom_info(self) -> list[int | str]:
        self._queue_info.queue.clear()
        self._write_line(self.custom_info_str)
        return self._get_and_check_info(self.custom_info_size)

    def _cast_splitted_input_string(self, line: list[int | str]) -> list[int | float]:
        line_parsed: list[int | float] = []

        for value, data_type in zip(line, self._data_structure.values()):
            # parsed_value = value if isinstance(value, data_type) else data_type(value)
            parsed_value = data_type(value)

            line_parsed.append(parsed_value)

        return line_parsed

    #########################################
    ### Init methods
    def _init(
        self,
        serial_number: Optional[int] = None,
        port: Optional[str] = None,
        verb_freq: int = 1,
    ) -> None:
        self._shutdown_partector = False
        self._init_serial(serial_number, port)
        self._init_thread()
        self._init_data_structures()
        self._init_serial_data_structure()

        self._init_clear_buffers()
        self.start()
        self._init_get_device_info()

        self.set_verbose_freq(verb_freq)

    def _init_serial(
        self, serial_number: Optional[int] = None, port: Optional[str] = None
    ) -> None:
        from naneos.partector import scan_for_serial_partector

        self._serial_number = serial_number
        self._port = port

        if self._serial_number:
            self._port = scan_for_serial_partector(serial_number=self._serial_number)
        elif self._port is None:
            raise Exception("No serial number or port given!")

        if self._port:
            self._ser = serial.Serial(
                port=self._port,
                baudrate=self.SERIAL_BAUDRATE,
                timeout=self.SERIAL_TIMEOUT,
            )

        # check type of self._ser
        if isinstance(self._ser, serial.Serial) and self._ser.is_open:
            self._connected = True
            logger.info(f"Connected to SN{self._serial_number} on {self._port}")

        self.set_verbose_freq(0)

    def _init_thread(self) -> None:
        Thread.__init__(self)
        self.name = "naneos-partector-thread"
        self.thread_event = Event()

    def _init_data_structures(self) -> None:
        self.custom_info_str = "0"
        self.custom_info_size = 0
        # will be declared in child class
        self._data_structure: dict[str, type[int | float]] = {}
        self._queue: Queue[list[int | str]] = Queue(maxsize=self.SERIAL_QUEUE_MAXSIZE)
        self._queue_info: Queue[list[int | str]] = Queue(maxsize=self.SERIAL_INFO_QUEUE_MAXSIZE)

    @abstractmethod
    def _init_serial_data_structure(self) -> None:
        pass

    def _init_clear_buffers(self) -> None:
        if not self._connected:
            return

        time.sleep(10e-3)
        if isinstance(self._ser, serial.Serial):
            self._ser.reset_input_buffer()

    def _init_get_device_info(self) -> None:
        try:
            if self._serial_number is None:
                self._serial_number = self._get_serial_number_secure()
            self._firmware_version = self.get_firmware_version()
            logger.debug(f"Connected to SN{self._serial_number} on {self._port}")
        except Exception:
            logger.warning("Could not get device info!")


if __name__ == "__main__":
    from naneos.partector import Partector2, Partector2ProGarage  # noqa: F401

    def test_callback(state: bool) -> None:
        logger.info(f"Catalyst state changed to {state}.")

    partector = Partector2ProGarage(
        serial_number=8421, callback_catalyst=test_callback, verb_freq=0
    )
    # partector = Partector2(serial_number=8112)

    time.sleep(20)

    print(partector.get_data_pandas())
    partector.close(blocking=True)

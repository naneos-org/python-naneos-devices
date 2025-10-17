import time
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timezone
from threading import Event, Thread
from typing import Any, Callable, Optional, Union

import serial

from naneos.logger import LEVEL_WARNING, get_naneos_logger
from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint
from naneos.partector.blueprints._partector_defaults import PartectorDefaults

logger = get_naneos_logger(__name__, LEVEL_WARNING)


class PartectorBluePrint(Thread, PartectorDefaults, ABC):
    """
    Class with the basic functionality of every Partector.
    Mandatory device specific methods are defined abstract and have to be implemented in the child class.
    """

    def __init__(
        self,
        serial_number: Optional[int] = None,
        port: Optional[str] = None,
        verb_freq: int = 1,
        hw_version: str = "None",
    ) -> None:
        """Initializes the Partector2 and starts the reading thread."""
        super().__init__()

        self._init_variables()
        self._verb_freq = verb_freq
        self._init(serial_number, port, verb_freq, hw_version)

    def _init_variables(self) -> None:
        self.device_type: int = 0  # gets initalized by child class
        self._connected = False
        self._sn: Optional[int] = None
        self._port: Optional[str] = None
        self._ser: serial.Serial = serial.Serial()
        self._time_last_message_received = time.time()
        self._legacy_data_structure: bool = False
        self._wait_with_data_output_until = time.time()

    #########################################
    ### Init methods
    def _init(
        self,
        serial_number: Optional[int] = None,
        port: Optional[str] = None,
        verb_freq: int = 1,
        hw_version: str = "None",
    ) -> None:
        self._hw_version = hw_version
        self._shutdown_partector = False
        self._init_serial(serial_number, port)
        self._init_thread()
        self._init_data_structures()
        self._init_clear_buffers()
        self.start()  # starts the checker thread

        self._init_get_device_info()

        self._init_serial_data_structure()
        self.set_verbose_freq(verb_freq)

        self._init_print_connection_info()

    def _init_print_connection_info(self) -> None:
        logger.info(f"Connected to SN{self._sn} on {self._port}")

    def _init_serial(self, serial_number: Optional[int] = None, port: Optional[str] = None) -> None:
        self._sn = serial_number
        self._port = port

        self._init_serial_sn_search()
        self._init_serial_connection()

        self._check_connection()

    def _init_serial_sn_search(self) -> None:
        from naneos.partector.scanPartector import scan_for_serial_partector

        if self._sn is not None:
            for _ in range(self.SERIAL_INIT_SCAN_RETRIES):
                self._port = scan_for_serial_partector(self._sn, self._hw_version)
                if self._port:
                    break
            if not self._port:
                logger.warning(
                    f"SN{self._sn} {self._port} not found! Checker is running in the background."
                )
        elif self._port is None:
            raise Exception("No serial number or port given!")

    def _init_serial_connection(self) -> None:
        tries = 0
        tries_start = time.time()

        if self._port is None:
            logger.error("No port given! Cannot initialize serial connection.")
            return

        while time.time() - tries_start < self.SERIAL_INIT_RETRIES_TIMEOUT_S:
            tries += 1

            try:
                self._ser = serial.Serial(
                    port=self._port,
                    baudrate=self.SERIAL_BAUDRATE,
                    timeout=self.SERIAL_TIMEOUT,
                )
            except serial.SerialException:
                continue
            if self._ser.is_open:
                self.set_verbose_freq(0)
                time.sleep(10e-3)
                self._ser.reset_input_buffer()
                break
            self._ser.close()

        if not self._ser.is_open:
            logger.error(f"SN{self._sn} on port {self._port} could not be opened! Tries: {tries}")
        if tries > 1:
            logger.warning(f"SN{self._sn} on port {self._port} needed {tries} tries to connect.")

    def _check_connection(self) -> None:
        if self._ser.is_open:
            self._connected = True
        else:
            self._connected = False
            logger.warning(f"Could not connect to SN{self._sn} on {self._port}")

    def _init_thread(self) -> None:
        self.name = f"naneos-partector-thread_{self._sn}"
        self.thread_event = Event()

    def _init_data_structures(self) -> None:
        self.custom_info_str = "0"
        self.custom_info_size = 0
        # will be declared in child class
        self._data_structure: dict[str, type[Union[int, float]]] = {}
        self._queue: deque[list[Union[int, str]]] = deque(maxlen=self.SERIAL_QUEUE_MAXSIZE)
        self._queue_info: deque[list[Union[int, str]]] = deque(
            maxlen=self.SERIAL_INFO_QUEUE_MAXSIZE
        )

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
            if self._sn is None:
                self._sn = self._get_serial_number_secure()
            self._fw = self.get_firmware_version()
            self._integration_time = self.get_integration_time_seconds()
            logger.debug(f"Connected to SN{self._sn} on {self._port}")
        except Exception:
            logger.warning("Could not get device info!")

    def close(
        self, blocking: bool = True, shutdown: bool = False, verbose_reset: bool = True
    ) -> None:
        """Closes the serial connection and stops the reading thread."""
        self._close(blocking, shutdown, verbose_reset)

    def _checker_thread(self) -> None:
        while not self.thread_event.wait(0.5):
            if time.time() - self._time_last_message_received > 10:
                try:
                    logger.info(f"SN{self._sn} {self._port}: Checking device connection...")
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

    def get_firmware_version(self) -> int:
        """Gets the firmware version via command from the device."""
        fw = self._serial_wrapper(self._get_firmware_version)
        if isinstance(fw, int):
            return fw
        return 0

    def get_integration_time_seconds(self) -> int:
        """Gets the integration time via command from the device."""
        it = self._serial_wrapper(self._get_integration_time)
        if isinstance(it, int):
            return it
        return 0

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

        if number_of_elem == 0:
            self._write_line(line)
            return []

        return self._serial_wrapper(self._custom_info)  # type: ignore

    #########################################
    ### User accessible data methods
    def clear_data_cache(self) -> None:
        """Clears the data cache."""
        # self._queue.clear()
        if isinstance(self._queue, deque) and len(self._queue) > 0:
            self._queue = deque([self._queue.pop()], maxlen=self.SERIAL_QUEUE_MAXSIZE)

    def get_data(self) -> list[NaneosDeviceDataPoint]:
        points: list[NaneosDeviceDataPoint] = []

        serial_data = list(self._queue)[0:-1]
        self.clear_data_cache()

        for line in serial_data:
            try:
                data_casted = self._cast_splitted_input_string(line)
                point = self._create_naneos_device_point(data_casted)
                points.append(point)
            except Exception as excep:
                logger.warning(f"Could not cast data: {excep}")
                logger.warning(f"Data: {line}")

        return points

    #########################################
    ### Serial methods (private)
    def _close(self, blocking: bool, shutdown: bool, verbose_reset: bool) -> None:
        try:
            if verbose_reset:
                self.set_verbose_freq(0)
                self._write_line("opd00!")
                self._write_line("h2000!")
                self._write_line("e0000!")
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
            if self._ser.is_open:
                self._serial_reading_routine()
        except Exception as e:
            logger.warning(
                f"SN{self._sn} {self._port} Exception occured during threaded serial reading: {e}"
            )

    def _run_check_connection(self) -> bool:
        """Checks if the device is still connected."""
        if not self._connected:
            logger.warning(f"SN{self._sn} {self._port} is not connected! (1)")
            self._init_serial(self._sn, self._port)
            self.set_verbose_freq(self._verb_freq)
            if self._connected:
                self._init_print_connection_info()
        elif self._check_device_connection() is False:
            logger.warning(f"SN{self._sn} {self._port} is not connected! (2)")
            if isinstance(self._ser, serial.Serial) and self._ser.is_open:
                self._ser.close()
            self._connected = False
            self._port = None

        return self._connected

    def _serial_reading_routine(self) -> None:
        if not self._connected:
            return

        line = self._read_line()

        if not line or line == "":
            return

        unix_timestamp = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        data = [unix_timestamp] + line.split("\t")

        self._notify_message_received()

        if not self._data_structure or len(data) < len(self._data_structure):
            self._queue_info.append(data)

        if time.time() < self._wait_with_data_output_until:
            return  # skip data output until time is over

        if len(data) == len(self._data_structure):
            self._queue.append(data)
        # this is legacy mode, where the data structure is not known exactly
        elif len(data) > len(self._data_structure) and self._legacy_data_structure:
            self._queue.append(data[0 : len(self._data_structure)])

    def _check_device_connection(self) -> bool:
        if self.thread_event.is_set() or not self._ser or not self._ser.is_open:
            return False

        try:
            sn = self._get_serial_number_secure()
            if sn == self._sn:
                return True

        except Exception as e:
            logger.error(f"Exception occured during device connection check: {e}")

        return False

    def _check_serial_connection(self) -> None:
        """Tries to reopen a closed connection. Raises exceptions on failure."""
        try:
            for _ in range(3):
                if not self._ser:
                    self._init_serial(self._sn, self._port)
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

        logger_msg = ""

        for _ in range(self.SERIAL_RETRIES):
            try:
                return func()
            except Exception as e:
                logger_msg = f"SN{self._sn} Exception occured during user function call: {e}"

        logger.warning(logger_msg)

        return False

    def _write_line(self, line: str) -> None:
        if not self._connected:
            return

        self._check_serial_connection()
        if self._ser:
            self._ser.write(line.encode())
            # time.sleep(10e-3)

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

    def _get_and_check_info(self, expected_length: int = 2) -> list[Union[int, str]]:
        """
        Get information from the queue and check its length.

        Parameters:
            expected_length (int): The expected length of the information.

        Returns:
            list: The information from the queue.

        Raises:
            ValueError: If the length of the information does not match the expected length.
        """
        # info_data = self._queue_info.get(timeout=self.SERIAL_TIMEOUT_INFO)
        info_data = []
        start_time = time.time()
        while time.time() - start_time < self.SERIAL_TIMEOUT_INFO:
            if len(self._queue_info) > 0:
                info_data = self._queue_info.popleft()
                break
            time.sleep(0.005)
        self._queue_info.clear()

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
        self._queue_info.clear()
        self._write_line("N?")
        return int(self._get_and_check_info()[1])

    def _get_firmware_version(self) -> Optional[int]:
        self._queue_info.clear()
        self._write_line("f?")
        fw = self._get_and_check_info()[1]
        try:
            fw = int(fw)
            return fw
        except Exception as e:
            logger.error(f"Could not cast firmware version to int: {e}")
            return None

    def _get_integration_time(self) -> Optional[int]:
        self._queue_info.clear()
        self._write_line("H?")
        it = self._get_and_check_info()[1]
        try:
            it = int(it)
            it = int(2 ** (it + 1))  # convert to seconds
            return it
        except Exception as e:
            logger.error(f"Could not cast firmware version to int: {e}")
            return None

    def _custom_info(self) -> list[Union[int, str]]:
        self._queue_info.clear()
        self._write_line(self.custom_info_str)
        return self._get_and_check_info(self.custom_info_size)

    def _cast_splitted_input_string(self, line: list[Union[int, str]]) -> list[Union[int, float]]:
        line_parsed: list[Union[int, float]] = []

        for value, data_type in zip(line, self._data_structure.values()):
            # parsed_value = value if isinstance(value, data_type) else data_type(value)
            parsed_value = data_type(value)

            line_parsed.append(parsed_value)

        return line_parsed

    def _create_naneos_device_point(self, data: list[Union[int, float]]) -> NaneosDeviceDataPoint:
        """
        Creates a NaneosDeviceDataPoint from the given data.

        Args:
            data (list): The data to create the NaneosDeviceDataPoint from.

        Returns:
            NaneosDeviceDataPoint: The created NaneosDeviceDataPoint.
        """
        point = NaneosDeviceDataPoint(
            device_type=self.device_type,
            serial_number=self._sn,
            connection_type=NaneosDeviceDataPoint.CONN_TYPE_SERIAL,
            firmware_version=self._fw,
        )

        for i, name in enumerate(self._data_structure.keys()):
            setattr(point, name, data[i])

        return point

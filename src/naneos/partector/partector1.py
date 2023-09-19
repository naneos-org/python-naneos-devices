import time
from datetime import datetime, timezone
from queue import Queue
from threading import Event, Thread

import pandas
import serial

from naneos.partector._data_structure import PARTECTOR1_DATA_STRUCTURE
from naneos.partector._lambda_upload import _get_lambda_upload_list_serial


class Partector1(Thread):
    SERIAL_RETRIES = 5  # MAGIC, number of retries when command fails
    TIMEOUT_SER = 0.1  # MAGIC, timeout of serial connection
    TIMEOUT_INFO = TIMEOUT_SER + 0.05  # MAGIC, timeout of info functions

    def __init__(self, port: str, verb_freq: int = 1) -> None:
        self.__init_serial(port)
        self.__init_thread()
        self.__init_data_structures()

        time.sleep(10e-3)
        self._ser.reset_input_buffer()
        self.last_heard = time.time()
        self.start()  # starts the thread

        self.__init_get_device_info()

        self.set_verbose_freq(verb_freq)

    def close(self, blocking: bool = True):
        self.STOP_EVENT.set()
        if blocking:
            self.join()

    def __init_thread(self):
        Thread.__init__(self)
        self.name = "naneos-partector1-serial"
        self.STOP_EVENT = Event()

    def __init_data_structures(self):
        self._data = Queue()
        self._info = Queue()

    def __init_serial(self, port: str):
        self._ser = serial.Serial(port=port, baudrate=9600, timeout=self.TIMEOUT_SER)
        self.set_verbose_freq(0)

    def __init_get_device_info(self):
        try:
            self._serial_number = self.get_serial_number_secure()
            self._firmware_version = self.get_firmware_version()
        except Exception:
            port = self._ser.port
            self.close()
            raise ConnectionError(f"No partector1 on port {port}.")

    def run(self):
        while not self.STOP_EVENT.is_set():
            try:
                self.__serial_reading_routine()
            except Exception as e:
                if not self.__check_device_connection():
                    self.close(blocking=False)
                    p = self._ser.port
                    self._ser.close()
                    raise Exception(f"P1 on port {p} disconnected! Prev exception: {e}")
                    # TODO: raise CUSTOM exception here

        self._ser.close()

    def __serial_reading_routine(self):
        data = [datetime.now(tz=timezone.utc)] + self._readline().split("\t")

        lenData = len(data)

        if lenData < len(PARTECTOR1_DATA_STRUCTURE):
            self._info.put(data)
            return

        if lenData > len(PARTECTOR1_DATA_STRUCTURE):
            data = data[: len(PARTECTOR1_DATA_STRUCTURE)]
        self._data.put(data)
        self.last_heard = time.time()

    def __check_device_connection(self):
        """Checks if P2 is still connected!"""
        if self.STOP_EVENT.is_set():
            return False

        try:
            sn = self.get_serial_number_secure()
            if sn != self._serial_number:
                raise Exception(f"SN changed from {self._serial_number} to {sn}")
        except Exception:
            return False

        return True

    # serial methods
    def __check_serial_connection(self):
        """Tries to reopen a closed connection. Raises exceptions on failure."""
        for _ in range(3):
            self._ser.open() if not self._ser.isOpen() else None
            if self._ser.isOpen():
                return None
        raise Exception("Was not able to open the Serial connection.")

    def _write(self, line: str):
        self.__check_serial_connection()
        self._ser.write(line.encode())

    def _readline(self) -> str:
        try:
            self.__check_serial_connection()
            data = self._ser.readline().decode()
            return data.replace("\r", "").replace("\n", "").replace("\x00", "")
        except Exception as e:
            self.last_heard = 0
            return ""

    # data methods
    def clear_data_cache(self):
        self._data.queue.clear()

    def get_data_list(self) -> list:
        """Returns the cache as list with timestamp as first element."""
        data_casted = []
        data = list(self._data.queue)
        self.clear_data_cache()

        for line in data:
            try:
                data_casted.append(self.__cast_splitted_input_string(line))
            except Exception as excep:
                print(f"Exception during casting (sp): {excep}")

        return data_casted

    def get_lambda_upload_list(self, data=None) -> list:
        if not data:
            data = self.get_data_list()
        return _get_lambda_upload_list_serial(data, self._serial_number)

    def get_data_pandas(self, data=None) -> pandas.DataFrame:
        if not data:
            data = self.get_data_list()

        columns = PARTECTOR1_DATA_STRUCTURE.keys()
        df = pandas.DataFrame(data, columns=columns).set_index("dateTime")
        return df

    def __cast_splitted_input_string(self, line: str):
        for i, data_type in enumerate(PARTECTOR1_DATA_STRUCTURE.values()):
            if type(line[i]) is not data_type:
                line[i] = data_type(line[i])

        return line

    # user wrappers
    def __user_wrapper(self, func):
        """Wraps user func in try-except block. Forwards exceptions to the user."""
        for _ in range(self.SERIAL_RETRIES):
            try:
                return func()
            except Exception as e:
                excep = f"Exception occured during user function call: {e}"
        raise Exception(excep)

    def get_serial_number(self) -> int:
        return self.__user_wrapper(self.__get_serial_number)

    def get_serial_number_secure(self) -> int:
        for _ in range(3):
            serial_numbers = [self.get_serial_number() for _ in range(3)]
            if all(x == serial_numbers[0] for x in serial_numbers):
                return serial_numbers[0]
        raise Exception("Was not able to fetch the serial number (secure)!")

    def get_firmware_version(self) -> str:
        return self.__user_wrapper(self.__get_firmware_version)

    def set_verbose_freq(self, freq: int):
        self.__set_verbose_freq(freq)

    # user protected methods
    def __get_and_check_info(self, leng: int = 2) -> list:
        data = self._info.get(timeout=self.TIMEOUT_INFO)
        if len(data) != 2:
            raise Exception(f"Info length {len(data)} not matching {leng}: {data}")
        return data

    def __get_serial_number(self) -> int:
        self._info.queue.clear()
        self._write("N?")
        return int(self.__get_and_check_info()[1])

    def __get_firmware_version(self) -> str:
        self._info.queue.clear()
        self._write("f?")
        return int(self.__get_and_check_info()[1])

    # TODO: check if frequency was set the right way
    # TODO: Ask Martin for an X? option in the protocol
    def __set_verbose_freq(self, freq: int):
        self._write(f"X000{freq}!")

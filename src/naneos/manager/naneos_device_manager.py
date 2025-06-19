import threading
import time

import pandas as pd

from naneos.iotweb.naneos_upload_thread import NaneosUploadThread
from naneos.logger import LEVEL_INFO, get_naneos_logger
from naneos.partector.blueprints._data_structure import (
    add_to_existing_naneos_data,
    sort_and_clean_naneos_data,
)
from naneos.partector.partector_serial_manager import PartectorSerialManager
from naneos.partector_ble.partector_ble_manager import PartectorBleManager

logger = get_naneos_logger(__name__, LEVEL_INFO)


class NaneosDeviceManager(threading.Thread):
    """
    NaneosDeviceManager is a class that manages Naneos devices.
    It connects and disconnects automatically.
    """

    UPLOAD_INTERVAL_SECONDS = 15

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self._next_upload_time = time.time() + self.UPLOAD_INTERVAL_SECONDS

        self._manager_serial = PartectorSerialManager()
        self._manager_ble = PartectorBleManager()

        self._data: dict[int, pd.DataFrame] = {}  # Store data from both serial and BLE managers

    def run(self) -> None:
        self._manager_serial.start()
        self._manager_ble.start()

        self._loop()

        self._manager_serial.stop()
        self._manager_ble.stop()

        self._manager_serial.join()
        self._manager_ble.join()

    def stop(self) -> None:
        self._stop_event.set()

    def get_connected_serial_devices(self) -> list[str]:
        """
        Returns a list of connected serial devices.
        """
        return self._manager_serial.get_connected_device_strings()

    def get_connected_ble_devices(self) -> list[str]:
        """
        Returns a list of connected BLE devices.
        """
        return self._manager_ble.get_connected_device_strings()

    def get_seconds_until_next_upload(self) -> float:
        """
        Returns the number of seconds until the next upload.
        This is used to determine when to upload data.
        """
        return max(0, self._next_upload_time - time.time())

    def _loop(self) -> None:
        self._next_upload_time = time.time() + self.UPLOAD_INTERVAL_SECONDS

        while not self._stop_event.is_set():
            try:
                time.sleep(1)

                data_serial = self._manager_serial.get_data()
                data_ble = self._manager_ble.get_data()

                self._data = add_to_existing_naneos_data(self._data, data_serial)
                self._data = add_to_existing_naneos_data(self._data, data_ble)

                if time.time() >= self._next_upload_time:
                    self._next_upload_time = time.time() + self.UPLOAD_INTERVAL_SECONDS

                    upload_data = sort_and_clean_naneos_data(self._data)
                    self._data = {}

                    uploader = NaneosUploadThread(
                        upload_data, callback=lambda success: print(f"Upload success: {success}")
                    )
                    uploader.start()
                    uploader.join()

            except Exception as e:
                logger.exception(f"DeviceManager loop exception: {e}")


if __name__ == "__main__":
    manager = NaneosDeviceManager()
    manager.start()

    try:
        while True:
            time.sleep(1)
            print(f"Seconds until next upload: {manager.get_seconds_until_next_upload():.1f}")
            print(manager.get_connected_serial_devices())
            print(manager.get_connected_ble_devices())
            print()
    except KeyboardInterrupt:
        manager.stop()
        manager.join()
        print("NaneosDeviceManager stopped.")

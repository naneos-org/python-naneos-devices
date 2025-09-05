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

        self._manager_serial: PartectorSerialManager | None = None
        self._manager_ble: PartectorBleManager | None = None

        self._data: dict[int, pd.DataFrame] = {}

        self._use_serial = True
        self._use_ble = True

    def use_serial_connections(self, use: bool) -> None:
        self._use_serial = use

    def use_ble_connections(self, use: bool) -> None:
        self._use_ble = use

    def get_serial_connection_status(self) -> bool:
        return self._use_serial

    def get_ble_connection_status(self) -> bool:
        return self._use_ble

    def run(self) -> None:
        self._loop()

        # graceful shutdown in any case
        self._use_serial = False
        self._loop_serial_manager()
        self._use_ble = False
        self._loop_ble_manager()

    def stop(self) -> None:
        self._stop_event.set()

    def get_connected_serial_devices(self) -> list[str]:
        """
        Returns a list of connected serial devices.
        """
        if self._manager_serial is None:
            return []

        return self._manager_serial.get_connected_device_strings()

    def get_connected_ble_devices(self) -> list[str]:
        """
        Returns a list of connected BLE devices.
        """
        if self._manager_ble is None:
            return []

        return self._manager_ble.get_connected_device_strings()

    def get_seconds_until_next_upload(self) -> float:
        """
        Returns the number of seconds until the next upload.
        This is used to determine when to upload data.
        """
        return max(0, self._next_upload_time - time.time())

    def _loop_serial_manager(self) -> None:
        # normal operation
        if (
            isinstance(self._manager_serial, PartectorSerialManager)
            and self._manager_serial.is_alive()
        ):
            data_serial = self._manager_serial.get_data()
            self._data = add_to_existing_naneos_data(self._data, data_serial)
        # starting
        if self._manager_serial is None and self._use_serial:
            logger.info("Starting serial manager...")
            self._manager_serial = PartectorSerialManager()
            self._manager_serial.start()
        # stopping
        if isinstance(self._manager_serial, PartectorSerialManager) and not self._use_serial:
            logger.info("Stopping serial manager...")
            self._manager_serial.stop()
            self._manager_serial.join()
            self._manager_serial = None

    def _loop_ble_manager(self) -> None:
        # normal operation
        if isinstance(self._manager_ble, PartectorBleManager) and self._manager_ble.is_alive():
            data_ble = self._manager_ble.get_data()
            self._data = add_to_existing_naneos_data(self._data, data_ble)
        # starting
        if self._manager_ble is None and self._use_ble:
            logger.info("Starting BLE manager...")
            self._manager_ble = PartectorBleManager()
            self._manager_ble.start()
        # stopping
        if isinstance(self._manager_ble, PartectorBleManager) and not self._use_ble:
            logger.info("Stopping BLE manager...")
            self._manager_ble.stop()
            self._manager_ble.join()
            self._manager_ble = None

    def _loop(self) -> None:
        self._next_upload_time = time.time() + self.UPLOAD_INTERVAL_SECONDS

        while not self._stop_event.is_set():
            try:
                time.sleep(1)

                self._loop_serial_manager()

                self._loop_ble_manager()

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

    counter = 0
    try:
        while True:
            counter += 1
            time.sleep(1)
            print(f"Seconds until next upload: {manager.get_seconds_until_next_upload():.0f}")
            print(manager.get_connected_serial_devices())
            print(manager.get_connected_ble_devices())
            print()

            if counter == 20:
                manager.use_serial_connections(False)
                manager.use_ble_connections(False)
                print("Disabled serial and BLE connections.")
            elif counter == 40:
                manager.use_serial_connections(True)
                manager.use_ble_connections(False)
                print("Enabled serial and disabled BLE connections.")
            elif counter == 60:
                manager.use_serial_connections(False)
                manager.use_ble_connections(True)
                print("Disabled serial and enabled BLE connections.")
            elif counter == 80:
                manager.use_serial_connections(True)
                manager.use_ble_connections(True)
                print("Enabled serial and BLE connections.")
    except KeyboardInterrupt:
        manager.stop()
        manager.join()
        print("NaneosDeviceManager stopped.")

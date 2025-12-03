import os
import queue
import signal
import threading
import time

import pandas as pd

from naneos.iotweb.naneos_upload_thread import NaneosUploadThread
from naneos.logger import LEVEL_WARNING, get_naneos_logger
from naneos.partector.blueprints._data_structure import (
    add_to_existing_naneos_data,
    sort_and_clean_naneos_data,
)
from naneos.partector.partector_serial_manager import PartectorSerialManager
from naneos.partector_ble.partector_ble_manager import PartectorBleManager

logger = get_naneos_logger(__name__, LEVEL_WARNING)


class NaneosDeviceManager(threading.Thread):
    """
    NaneosDeviceManager is a class that manages Naneos devices.
    It connects and disconnects automatically.
    """

    def __init__(
        self, use_serial=True, use_ble=True, upload_active=True, gathering_interval_seconds=30
    ) -> None:
        super().__init__(daemon=True)
        self._use_serial = use_serial
        self._use_ble = use_ble
        self._upload_active = upload_active
        self._next_upload_time = time.time() + gathering_interval_seconds
        self.set_gathering_interval_seconds(gathering_interval_seconds)

        self._out_queue: queue.Queue | None = None

        self._stop_event = threading.Event()

        self._manager_serial: PartectorSerialManager | None = None
        self._manager_ble: PartectorBleManager | None = None

        self._data: dict[int, pd.DataFrame] = {}

        self.upload_blocked_devices: list[int | None] = []

    def use_serial_connections(self, use: bool) -> None:
        self._use_serial = use

    def use_ble_connections(self, use: bool) -> None:
        self._use_ble = use

    def get_serial_connection_status(self) -> bool:
        return self._use_serial

    def get_ble_connection_status(self) -> bool:
        return self._use_ble

    def get_upload_status(self) -> bool:
        return self._upload_active

    def set_upload_status(self, active: bool) -> None:
        self._upload_active = active

    def get_gathering_interval_seconds(self) -> int:
        return self._gathering_interval_seconds

    def set_gathering_interval_seconds(self, interval: int) -> None:
        interval = max(10, min(600, interval))
        logger.info(f"Setting gathering interval to {interval} seconds.")
        self._gathering_interval_seconds = interval

        tmp_next_upload_time = time.time() + self._gathering_interval_seconds
        self._next_upload_time = min(self._next_upload_time, tmp_next_upload_time)

    def register_output_queue(self, out_queue: queue.Queue) -> None:
        self._out_queue = out_queue

    def unregister_output_queue(self) -> None:
        self._out_queue = None

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
            self.upload_blocked_devices = self._manager_serial.get_gain_test_activating_devices()
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
        self._next_upload_time = time.time() + self._gathering_interval_seconds

        while not self._stop_event.is_set():
            try:
                time.sleep(1)

                self._loop_serial_manager()
                self._loop_ble_manager()

                # remove entries from _data that is in upload_blocked_devices
                for blocked_sn in self.upload_blocked_devices:
                    if blocked_sn in self._data:
                        del self._data[blocked_sn]

                if time.time() >= self._next_upload_time:
                    self._next_upload_time = time.time() + self._gathering_interval_seconds

                    serial_connected_sns: list[int | None] = []
                    if self._use_serial and self._manager_serial is not None:
                        serial_connected_sns = self._manager_serial.get_connected_serial_numbers()

                    upload_data = sort_and_clean_naneos_data(self._data, serial_connected_sns)
                    self._data = {}

                    if isinstance(self._out_queue, queue.Queue):
                        self._out_queue.put(upload_data)

                    if self._upload_active:
                        uploader = NaneosUploadThread(
                            upload_data,
                            callback=lambda success: logger.info(f"Upload success: {success}"),
                        )
                        uploader.start()
                        uploader.join()

            except Exception as e:
                logger.exception(f"DeviceManager loop exception: {e}")


def minimal_example() -> None:
    manager = NaneosDeviceManager(
        use_serial=True,
        use_ble=True,
        upload_active=False,
        gathering_interval_seconds=10,  # clamped to [10, 600]
    )
    manager.start()

    try:
        while True:
            # Sleep exactly until the next publish window
            remaining = manager.get_seconds_until_next_upload()
            print(f"Next upload in: {remaining:.0f}s")
            time.sleep(remaining + 1)

            print("Serial:", manager.get_connected_serial_devices())
            print("BLE   :", manager.get_connected_ble_devices())
            print()
    except KeyboardInterrupt:
        pass

    manager.stop()
    manager.join()
    print("Stopped.")


def queue_example() -> None:
    import queue

    out_q: queue.Queue = queue.Queue()

    manager = NaneosDeviceManager(
        upload_active=True,
        gathering_interval_seconds=10,
        use_ble=True,
        use_serial=True,
    )
    manager.register_output_queue(out_q)
    manager.start()

    try:
        while True:
            # Wait until a snapshot is ready, then pull all pending ones
            time.sleep(manager.get_seconds_until_next_upload() + 1)

            while not out_q.empty():
                snapshot = out_q.get()
                # snapshot: dict[int, pandas.DataFrame] keyed by device serial
                print(f"Received snapshot for {len(snapshot)} device(s)")
                for serial, df in snapshot.items():
                    print(f"  - {serial}: {len(df)} rows, ldsa: {df['ldsa'].mean():.1f}")
                    # >>> Your processing here (store, analyze, forward, etc.)
                    # print(df.dropna(axis=1, how="all"))
    except KeyboardInterrupt:
        pass

    manager.stop()
    manager.join()


def raise_keyboard_interrupt():
    os.kill(os.getpid(), signal.SIGINT)


def test_naneos_device_manager():
    timer = threading.Timer(300, raise_keyboard_interrupt)  # trigger keyboard interrupt after 20s
    timer.start()

    manager = NaneosDeviceManager()
    manager.start()

    try:
        while True:
            time.sleep(1)
            print(f"Seconds until next upload: {manager.get_seconds_until_next_upload():.0f}")
            print(manager.get_connected_serial_devices())
            print(manager.get_connected_ble_devices())
            print()
    except KeyboardInterrupt:
        manager.stop()
        manager.join()
        print("NaneosDeviceManager stopped.")

    timer.cancel()


def ble_connect_example() -> None:
    manager = NaneosDeviceManager(
        use_serial=False,
        use_ble=True,
        upload_active=False,
        gathering_interval_seconds=10,  # clamped to [10, 600]
    )
    manager.start()

    try:
        while True:
            # check if 8617 is connected
            devices = manager.get_connected_ble_devices()
            if "SN8617" in devices:
                print("8617 is connected")
                manager.stop()
                manager.join()
                print("Stopped.")

                # restart
                manager = NaneosDeviceManager(
                    use_serial=False,
                    use_ble=True,
                    upload_active=False,
                    gathering_interval_seconds=10,  # clamped to [10, 600]
                )
                manager.start()
                print("Restarted.")

    except KeyboardInterrupt:
        pass

    manager.stop()
    manager.join()
    print("Stopped.")


if __name__ == "__main__":
    # minimal_example()
    queue_example()
    # test_naneos_device_manager()
    # ble_connect_example()

    # df = pd.read_pickle("partector_data_sn24.pkl")
    # print(df)

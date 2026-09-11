import queue
import threading
import time
from collections import deque
from typing import TypeVar

import pandas as pd

from naneos.frames import add_to_existing_naneos_data, sort_and_clean_naneos_data
from naneos.iotweb.naneos_upload_thread import NaneosUploadThread
from naneos.logger import get_naneos_logger
from naneos.partector.partector_serial_manager import PartectorSerialManager
from naneos.partector_ble.partector_ble_manager import PartectorBleManager

logger = get_naneos_logger(__name__)

ManagerT = TypeVar("ManagerT", PartectorSerialManager, PartectorBleManager)


class NaneosDeviceManager(threading.Thread):
    """Connects to every Partector on USB and BLE, gathers their data in snapshots
    and hands each snapshot to the output queue and / or the naneos upload."""

    # Snapshots whose upload failed are kept and retried on the next upload
    # tick, oldest first. With the default 30 s interval this covers a network
    # outage of about 10 minutes; older snapshots are dropped.
    MAX_PENDING_UPLOADS = 20

    def __init__(
        self,
        use_serial: bool = True,
        use_ble: bool = True,
        upload_active: bool = True,
        gathering_interval_seconds: int = 30,
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
        self._pending_uploads: deque[dict[int, pd.DataFrame]] = deque(
            maxlen=self.MAX_PENDING_UPLOADS
        )

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

    def get_pending_upload_count(self) -> int:
        """Number of snapshots waiting to be uploaded, including retries."""
        return len(self._pending_uploads)

    def get_seconds_until_next_upload(self) -> float:
        """
        Returns the number of seconds until the next upload.
        This is used to determine when to upload data.
        """
        return max(0, self._next_upload_time - time.time())

    def _loop_serial_manager(self) -> None:
        if self._manager_serial is not None and self._manager_serial.is_alive():
            self.upload_blocked_devices = self._manager_serial.get_gain_test_activating_devices()
            self._data = add_to_existing_naneos_data(self._data, self._manager_serial.get_data())

        self._manager_serial = self._sync_manager(
            self._manager_serial, self._use_serial, PartectorSerialManager, "serial"
        )

    def _loop_ble_manager(self) -> None:
        if self._manager_ble is not None and self._manager_ble.is_alive():
            self._data = add_to_existing_naneos_data(self._data, self._manager_ble.get_data())

        self._manager_ble = self._sync_manager(
            self._manager_ble, self._use_ble, PartectorBleManager, "BLE"
        )

    @staticmethod
    def _sync_manager(
        manager: ManagerT | None, wanted: bool, factory: type[ManagerT], name: str
    ) -> ManagerT | None:
        """Starts or stops a sub-manager so that it matches the wanted state."""
        if manager is None and wanted:
            logger.info(f"Starting {name} manager...")
            manager = factory()
            manager.start()
        elif manager is not None and not wanted:
            logger.info(f"Stopping {name} manager...")
            manager.stop()
            manager.join()
            manager = None
        return manager

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

                    self._publish_snapshot(upload_data)

            except Exception as e:
                logger.exception(f"DeviceManager loop exception: {e}")

    def _publish_snapshot(self, snapshot: dict[int, pd.DataFrame]) -> None:
        """Hand a gathered snapshot to the output queue and the uploader."""
        if isinstance(self._out_queue, queue.Queue):
            self._out_queue.put(snapshot)

        if not self._upload_active:
            return

        if snapshot:
            self._pending_uploads.append(snapshot)
        self._upload_pending()

    def _upload_pending(self) -> None:
        """Upload queued snapshots oldest first; stop at the first failure.

        The point timestamps are absolute, so a snapshot uploaded a few
        intervals late lands at the right time on the server.
        """
        while self._pending_uploads:
            outcome = self._try_upload(self._pending_uploads[0])
            if outcome == "retry":
                logger.warning(
                    f"Upload failed, keeping {len(self._pending_uploads)} snapshot(s) for retry."
                )
                return
            self._pending_uploads.popleft()

    @staticmethod
    def _try_upload(snapshot: dict[int, pd.DataFrame]) -> str:
        """Returns "ok", "retry" (network / server problem) or "drop" (rejected)."""
        try:
            response = NaneosUploadThread.upload(snapshot)
        except Exception as e:
            logger.warning(f"Upload failed: {e}")
            return "retry"

        if response.status_code == 200:
            logger.info("Upload success: True")
            return "ok"
        if response.status_code >= 500:
            logger.warning(f"Upload failed with HTTP {response.status_code}, will retry.")
            return "retry"

        # A 4xx will not get better by resending the same payload.
        logger.error(f"Upload rejected with HTTP {response.status_code}, dropping snapshot.")
        return "drop"

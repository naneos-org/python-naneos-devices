import queue
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from typing import TypeVar

import pandas as pd

from naneos.ble.partector.manager import PartectorBleManager
from naneos.cloud.upload import upload_snapshot
from naneos.device import PartectorDevice
from naneos.frames import add_to_existing_naneos_data, sort_and_clean_naneos_data
from naneos.logger import get_naneos_logger
from naneos.usb.partector.manager import PartectorSerialManager

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
        ble_serial_numbers: Iterable[int] | None = None,
        ble_max_links: int = PartectorBleManager.DEFAULT_MAX_LINKS,
        serial_gain_test: bool = True,
        serial_pulse_diagnostics: bool = True,
    ) -> None:
        """
        Args:
            use_serial: connect to Partectors on USB.
            use_ble: connect to Partectors over Bluetooth (data comes from the links only).
            upload_active: upload every snapshot to the naneos IoT service.
            gathering_interval_seconds: snapshot interval, clamped to 10-600 s.
            ble_serial_numbers: only link to these devices over BLE; None means any in reach.
            ble_max_links: upper bound of simultaneous BLE links.
            serial_gain_test: run the electrometer gain test on USB devices. Their data is
                held back for at least 10 s after every connect while it settles.
            serial_pulse_diagnostics: let USB devices report the pulse diagnostics.
        """
        super().__init__(daemon=True)
        self._use_serial = use_serial
        self._use_ble = use_ble
        self._ble_serial_numbers = frozenset(ble_serial_numbers) if ble_serial_numbers else None
        self._ble_max_links = ble_max_links
        self._serial_gain_test = serial_gain_test
        self._serial_pulse_diagnostics = serial_pulse_diagnostics
        self._upload_active = upload_active
        self._next_upload_time = time.time() + gathering_interval_seconds
        self.gathering_interval_seconds = gathering_interval_seconds

        self._out_queue: queue.Queue | None = None

        self._stop_event = threading.Event()

        self._manager_serial: PartectorSerialManager | None = None
        self._manager_ble: PartectorBleManager | None = None

        self._data: dict[int, pd.DataFrame] = {}
        self._pending_uploads: deque[dict[int, pd.DataFrame]] = deque(
            maxlen=self.MAX_PENDING_UPLOADS
        )

        self._upload_blocked_devices: list[int | None] = []

    # == Runtime controls ==========================================================================
    @property
    def use_serial(self) -> bool:
        """USB devices on / off. Takes effect within a second, also while running."""
        return self._use_serial

    @use_serial.setter
    def use_serial(self, use: bool) -> None:
        self._use_serial = use

    @property
    def use_ble(self) -> bool:
        """BLE devices on / off. Takes effect within a second, also while running;
        switching off waits for the links to disconnect."""
        return self._use_ble

    @use_ble.setter
    def use_ble(self, use: bool) -> None:
        self._use_ble = use

    @property
    def upload_active(self) -> bool:
        """Upload of the snapshots to the naneos IoT service on / off."""
        return self._upload_active

    @upload_active.setter
    def upload_active(self, active: bool) -> None:
        self._upload_active = active

    @property
    def gathering_interval_seconds(self) -> int:
        """Snapshot interval; values are clamped to 10-600 s."""
        return self._gathering_interval_seconds

    @gathering_interval_seconds.setter
    def gathering_interval_seconds(self, interval: int) -> None:
        interval = max(10, min(600, interval))
        logger.info(f"Setting gathering interval to {interval} seconds.")
        self._gathering_interval_seconds = interval

        tmp_next_upload_time = time.time() + self._gathering_interval_seconds
        self._next_upload_time = min(self._next_upload_time, tmp_next_upload_time)

    @property
    def pending_upload_count(self) -> int:
        """Number of snapshots waiting to be uploaded, including retries."""
        return len(self._pending_uploads)

    @property
    def seconds_until_next_snapshot(self) -> float:
        """Time until the next snapshot is put on the output queue and uploaded."""
        return max(0, self._next_upload_time - time.time())

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

    def get_devices(self) -> list[PartectorDevice]:
        """One handle per connected device, to write to it, query it and set its rate.

        A device that is reachable both ways is listed with its USB connection,
        like its data: USB is faster and the only way to change the data rate.
        """
        devices: dict[int | None, PartectorDevice] = {}
        for manager in (self._manager_ble, self._manager_serial):  # serial wins
            if manager is not None:
                devices.update({device.serial_number: device for device in manager.get_devices()})
        return list(devices.values())

    def get_device(self, serial_number: int) -> PartectorDevice:
        """The handle of one connected device.

        Raises:
            KeyError: no device with this serial number is connected.
        """
        for device in self.get_devices():
            if device.serial_number == serial_number:
                return device
        raise KeyError(f"SN{serial_number} is not connected.")

    def write(self, serial_number: int, command: str) -> None:
        """Send a command without an answer to a device, see PartectorDevice.write()."""
        self.get_device(serial_number).write(command)

    def query(self, serial_number: int, command: str, timeout: float | None = None) -> list[str]:
        """Send a command to a device and return its answer, see PartectorDevice.query()."""
        return self.get_device(serial_number).query(command, timeout)

    def set_sample_rate(self, serial_number: int, hz: int) -> None:
        """Set the data rate of a device on USB, see PartectorDevice.set_sample_rate().

        The output queue gets the data at this rate; the upload stays at 1 Hz.
        """
        self.get_device(serial_number).set_sample_rate(hz)

    def _loop_serial_manager(self) -> None:
        if self._manager_serial is not None and self._manager_serial.is_alive():
            self._upload_blocked_devices = self._manager_serial.get_settling_serial_numbers()
            self._data = add_to_existing_naneos_data(self._data, self._manager_serial.get_data())

        self._manager_serial = self._sync_manager(
            self._manager_serial,
            self._use_serial,
            lambda: PartectorSerialManager(self._serial_gain_test, self._serial_pulse_diagnostics),
            "serial",
        )

    def _loop_ble_manager(self) -> None:
        if self._manager_ble is not None and self._manager_ble.is_alive():
            self._data = add_to_existing_naneos_data(self._data, self._manager_ble.get_data())

        self._manager_ble = self._sync_manager(
            self._manager_ble,
            self._use_ble,
            lambda: PartectorBleManager(self._ble_serial_numbers, self._ble_max_links),
            "BLE",
        )

    @staticmethod
    def _sync_manager(
        manager: ManagerT | None, wanted: bool, factory: Callable[[], ManagerT], name: str
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

                # a device that is settling after a gain test start delivers no valid data
                for blocked_sn in self._upload_blocked_devices:
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
            response = upload_snapshot(snapshot)
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

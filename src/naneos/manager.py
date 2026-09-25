import queue
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from typing import TypeVar

import pandas as pd
from requests.exceptions import ReadTimeout

from naneos.ble.partector.manager import PartectorBleManager
from naneos.cloud.backlog import CHUNK_SECONDS, Chunk, Eviction, UploadBacklog
from naneos.cloud.upload import backend_status, prepare_frames, send_frames, upload_diagnostic
from naneos.data_point import ConnectionType, NaneosDeviceDataPoint
from naneos.device import NotSupportedError, PartectorDevice
from naneos.diagnostics import PulseForm, UiCurve
from naneos.frames import add_to_existing_naneos_data, sort_and_clean_naneos_data
from naneos.logger import get_naneos_logger
from naneos.usb.partector.manager import PartectorSerialManager

logger = get_naneos_logger(__name__)

ManagerT = TypeVar("ManagerT", PartectorSerialManager, PartectorBleManager)


class NaneosDeviceManager(threading.Thread):
    """Connects to every Partector on USB and BLE, gathers their data in snapshots
    and hands each snapshot to the output queue and / or the naneos upload."""

    # UI curves and pulse forms waiting for their upload: about 1 KB each, so
    # this is days of them. The snapshots wait in a backlog capped in MB.
    MAX_PENDING_DIAGNOSTICS = 500
    # A readout that comes back short (over BLE a lost packet) or not at all is read again,
    # this many attempts in all, before it is dropped: the backend spaces the entries by index,
    # so an incomplete curve or form would land in the database shifted.
    DIAGNOSTICS_ATTEMPTS = 3
    # A sweep holds the data of its device back for 15 to 30 s: more often than every half hour
    # is too disturbing. Less often than daily is not worth a schedule.
    MIN_DIAGNOSTICS_INTERVAL_HOURS = 0.5
    MAX_DIAGNOSTICS_INTERVAL_HOURS = 24
    # The most rows (all devices) in one request. The backend needs ~2.7 ms per data point, so
    # 2000 rows are ~6 s: well inside the timeout, and 7 devices at 600 s (4200 rows) are not.
    MAX_CHUNK_ROWS = 2000
    # The sender waits this long after a failed upload, growing to the last value.
    RETRY_DELAYS_SECONDS = (5, 10, 20, 40, 60)
    # A running sender is given this long to finish the request it is in.
    SENDER_JOIN_SECONDS = 12

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
        sample_rate_hz: int | None = None,
        diagnostics_interval_hours: float | None = 1.0,
        upload_buffer_mb: float = 100,
        ble_p2pro_mode: bool = True,
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
            sample_rate_hz: the data rate of the USB devices, see the property.
            diagnostics_interval_hours: read the UI curve and the pulse form of every
                connected device this often, 0.5 to 24 hours, see the property. None
                switches it off.
            upload_buffer_mb: what is kept in RAM while the upload does not work, in MB
                (a P2 at 1 Hz needs about 16 MB per day). The oldest data is dropped
                when it is full. It is lost when the process ends.
            ble_p2pro_mode: put a P2 Pro into size distribution mode after every BLE
                connect, as the USB connect does. Skipped for a device that is connected
                over USB, and for all devices while `sample_rate_hz` is set: USB decides
                their mode. False never touches the mode over BLE.
        """
        if not upload_buffer_mb > 0:
            raise ValueError("upload_buffer_mb must be positive.")
        super().__init__(daemon=True)
        self._use_serial = use_serial
        self._use_ble = use_ble
        self._ble_serial_numbers = frozenset(ble_serial_numbers) if ble_serial_numbers else None
        self._ble_max_links = ble_max_links
        self._ble_p2pro_mode = ble_p2pro_mode
        self._serial_gain_test = serial_gain_test
        self._serial_pulse_diagnostics = serial_pulse_diagnostics
        self._sample_rate_hz = PartectorSerialManager.check_sample_rate(sample_rate_hz)
        self._upload_active = upload_active
        self._next_upload_time = time.time() + gathering_interval_seconds
        self.gathering_interval_seconds = gathering_interval_seconds

        self._out_queue: queue.Queue | None = None
        self._live_queue: queue.Queue | None = None
        self._live_points_dropped = 0

        self.diagnostics_interval_hours = diagnostics_interval_hours
        self._diagnostics_queue: queue.Queue | None = None
        self._diagnostics_requested = threading.Event()
        self._diagnostics_thread: threading.Thread | None = None
        self._last_diagnostics_block: int | None = None
        self._pending_diagnostics: deque[UiCurve | PulseForm] = deque(
            maxlen=self.MAX_PENDING_DIAGNOSTICS
        )
        self._diagnostics_lock = threading.Lock()  # the readout thread appends, the sender pops

        self._stop_event = threading.Event()

        self._manager_serial: PartectorSerialManager | None = None
        self._manager_ble: PartectorBleManager | None = None

        self._data: dict[int, pd.DataFrame] = {}

        # The upload runs on a thread of its own, so a slow or missing network never
        # holds up the gathering: the loop puts snapshots into the backlog, the
        # sender takes them out.
        self._backlog = UploadBacklog(int(upload_buffer_mb * 1_000_000))
        self._sender: threading.Thread | None = None
        self._wake_sender = threading.Event()
        self._chunk_seconds = CHUNK_SECONDS  # halved when a server chokes on a big request
        self._retry_delay = 0
        self._diagnostics_retry_at = 0.0
        self._diagnostics_retry_delay = 0
        self._outage_since: float | None = None
        self._evicted = Eviction(0, 0)  # dropped since the last log line
        self._evicted_logged_at: float | None = None  # monotonic time of the last log line

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
    def sample_rate_hz(self) -> int | None:
        """The data rate of every USB device: 1, 10 or 100 Hz, or None for the
        default of each device (1 Hz, size distribution mode on a P2 Pro).
        Takes effect within a second, also while running; BLE stays at 1 Hz.
        The upload to naneos stays at 1 Hz whatever is set here.
        """
        return self._sample_rate_hz

    @sample_rate_hz.setter
    def sample_rate_hz(self, hz: int | None) -> None:
        self._sample_rate_hz = PartectorSerialManager.check_sample_rate(hz)
        if self._manager_serial is not None:
            self._manager_serial.sample_rate_hz = hz

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
    def diagnostics_interval_hours(self) -> float | None:
        """How often the UI curve and the pulse form of every connected device are read
        and uploaded, 0.5 to 24 hours, None for never. The readouts happen at the wall clock
        multiples of the interval (with 1 h: on the hour), one device after the other, so a
        change takes effect at the next multiple; request_diagnostics() reads now.

        A UI curve sweep disturbs the measurement: the data points of the device are
        held back for about 15 s (USB) to 30 s (BLE) per readout.
        """
        return self._diagnostics_interval_hours

    @diagnostics_interval_hours.setter
    def diagnostics_interval_hours(self, hours: float | None) -> None:
        if hours is not None and not (
            self.MIN_DIAGNOSTICS_INTERVAL_HOURS <= hours <= self.MAX_DIAGNOSTICS_INTERVAL_HOURS
        ):
            raise ValueError(
                f"The diagnostics interval must be {self.MIN_DIAGNOSTICS_INTERVAL_HOURS:g} to "
                f"{self.MAX_DIAGNOSTICS_INTERVAL_HOURS:g} hours, or None for never."
            )
        self._diagnostics_interval_hours = hours
        self._last_diagnostics_block = None  # the next multiple counts from now

    @property
    def pending_upload_count(self) -> int:
        """Number of snapshots waiting to be uploaded, including retries.

        The request that is being sent right now is not counted.
        """
        return self._backlog.snapshots

    @property
    def pending_upload_seconds(self) -> int:
        """Seconds of data waiting to be uploaded (per chunk, devices in parallel)."""
        return self._backlog.seconds

    @property
    def pending_upload_bytes(self) -> int:
        """RAM the data waiting to be uploaded takes, of upload_buffer_mb."""
        return self._backlog.size_bytes

    @property
    def pending_diagnostics_count(self) -> int:
        """Number of UI curves and pulse forms waiting to be uploaded, including retries."""
        return len(self._pending_diagnostics)

    def register_diagnostics_queue(self, diagnostics_queue: queue.Queue) -> None:
        """Every UiCurve and PulseForm the manager reads is put on this queue, whether
        it was read on the interval or with request_diagnostics(). Only complete ones (100
        U + 100 I values, 200 I values) get here; see DIAGNOSTICS_ATTEMPTS."""
        self._diagnostics_queue = diagnostics_queue

    def unregister_diagnostics_queue(self) -> None:
        self._diagnostics_queue = None

    def request_diagnostics(self) -> None:
        """Read the UI curve and the pulse form of every connected device now, one
        device after the other, on a thread of the manager. Returns at once; the
        results go to the diagnostics queue and the upload like the periodic ones."""
        self._diagnostics_requested.set()

    @property
    def diagnostics_in_progress(self) -> bool:
        """True while the manager is reading the diagnostics of its devices."""
        thread = self._diagnostics_thread
        return thread is not None and thread.is_alive()

    @property
    def seconds_until_next_snapshot(self) -> float:
        """Time until the next snapshot is put on the output queue and uploaded."""
        return max(0, self._next_upload_time - time.time())

    def register_output_queue(self, out_queue: queue.Queue) -> None:
        """Every snapshot (dict[int, pandas.DataFrame]) is put on this queue."""
        self._out_queue = out_queue

    def unregister_output_queue(self) -> None:
        self._out_queue = None

    def register_live_queue(self, live_queue: queue.Queue) -> None:
        """Every NaneosDeviceDataPoint is put on this queue the moment it arrives.

        Independent of the snapshots and the upload, at the rate of the device
        (see set_sample_rate). A device that is connected over USB and BLE
        delivers its USB points only.

        Give the queue a maxsize: when it is full the oldest point is dropped
        to make room (see live_points_dropped), so a consumer that falls
        behind loses old data instead of stalling the devices. An unbounded
        queue grows without limit when nobody reads it.
        """
        self._live_queue = live_queue

    def unregister_live_queue(self) -> None:
        self._live_queue = None

    @property
    def live_points_dropped(self) -> int:
        """Points dropped from the live queue because it was full."""
        return self._live_points_dropped

    def _ble_may_set_p2pro_mode(self, serial_number: int) -> bool:
        """Asked by a BLE link before it switches a P2 Pro into size distribution mode.

        Runs on the BLE event loop. USB decides the mode of a device that is connected over
        USB, and of all devices while a rate is set (a rate means the plain P2 mode).
        """
        if self._sample_rate_hz is not None:
            return False
        serial_manager = self._manager_serial
        return (
            serial_manager is None
            or serial_number not in serial_manager.get_connected_serial_numbers()
        )

    def _on_live_point(self, point: NaneosDeviceDataPoint) -> None:
        """Runs on the serial reader threads and the BLE event loop: never blocks."""
        live_queue = self._live_queue
        if live_queue is None:
            return

        if point.connection_type == ConnectionType.CONNECTED:
            serial_manager = self._manager_serial
            if (
                serial_manager is not None
                and point.serial_number in serial_manager.get_connected_serial_numbers()
            ):
                return  # the USB connection of this device delivers the same measurement

        try:
            live_queue.put_nowait(point)
            return
        except queue.Full:
            pass

        # Drop the oldest point. Another producer may win the freed slot, then this
        # point is the one that is lost; either way nothing blocks.
        self._live_points_dropped += 1
        try:
            live_queue.get_nowait()
            live_queue.put_nowait(point)
        except (queue.Empty, queue.Full):
            pass

    def run(self) -> None:
        self._sender = threading.Thread(target=self._sender_loop, name="naneos-upload", daemon=True)
        self._sender.start()
        self._loop()

        # graceful shutdown in any case
        self._use_serial = False
        self._loop_serial_manager()
        self._use_ble = False
        self._loop_ble_manager()
        self._sender.join(timeout=self.SENDER_JOIN_SECONDS)

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_sender.set()

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

    def set_sample_rate(self, serial_number: int, hz: int | None) -> None:
        """Set the data rate of one device on USB, see PartectorDevice.set_sample_rate().
        For all devices at once, and for the ones that connect later, set sample_rate_hz.

        The output queue gets the data at this rate; the upload stays at 1 Hz.
        """
        self.get_device(serial_number).set_sample_rate(hz)

    def read_ui_curve(self, serial_number: int, timeout: float | None = None) -> UiCurve:
        """Read the UI curve of one device, see PartectorDevice.read_ui_curve().
        Blocks for 15 s or more; the result is returned, not uploaded."""
        return self.get_device(serial_number).read_ui_curve(timeout)

    def read_pulse_form(self, serial_number: int, timeout: float | None = None) -> PulseForm:
        """Read the pulse form of one device, see PartectorDevice.read_pulse_form().
        The result is returned, not uploaded."""
        return self.get_device(serial_number).read_pulse_form(timeout)

    # == Diagnostics ===============================================================================
    def _tick_diagnostics(self) -> None:
        """Once a second on the manager thread: start the readouts when they are due."""
        interval = self._diagnostics_interval_hours
        if interval is not None:
            block = int(time.time() // (interval * 3600))
            if self._last_diagnostics_block is None:
                self._last_diagnostics_block = block  # the first readout at the next multiple
            elif block != self._last_diagnostics_block:
                self._last_diagnostics_block = block
                self._diagnostics_requested.set()

        if self._diagnostics_requested.is_set() and not self.diagnostics_in_progress:
            self._diagnostics_requested.clear()
            self._diagnostics_thread = threading.Thread(
                target=self._read_all_diagnostics, name="naneos-diagnostics", daemon=True
            )
            self._diagnostics_thread.start()

    def _read_all_diagnostics(self) -> None:
        """One device after the other: the readouts hold the command lock of their
        device, and the BLE links share one radio."""
        for device in self.get_devices():
            if self._stop_event.is_set():
                return
            # The curve first: a "UI!" interrupts a pulse form that is still streaming.
            for what, read in (
                ("UI curve", device.read_ui_curve),
                ("pulse form", device.read_pulse_form),
            ):
                try:
                    result = self._read_diagnostic(device, what, read)
                except NotSupportedError as e:
                    logger.debug(f"SN{device.serial_number}: no diagnostics: {e}")
                    break
                if result is not None:
                    self._publish_diagnostic(result)

    def _read_diagnostic(
        self, device: PartectorDevice, what: str, read: Callable[[], UiCurve | PulseForm]
    ) -> UiCurve | PulseForm | None:
        """Read one UI curve or pulse form that has all its entries.

        A result with too few or too many entries, or none within the timeout, is read again,
        DIAGNOSTICS_ATTEMPTS attempts in all (a UI curve retry sweeps again). Returns None
        when no attempt was complete, or when the device failed in a way that a retry does
        not help (not connected): only complete results are ever published.

        Raises:
            NotSupportedError: the device has no such diagnostic.
        """
        link = "USB" if device.connection_type == ConnectionType.SERIAL else "BLE"
        who = f"SN{device.serial_number} over {link}"
        attempts = self.DIAGNOSTICS_ATTEMPTS
        problem = ""

        for attempt in range(1, attempts + 1):
            if self._stop_event.is_set():
                return None
            try:
                result = read()
            except NotSupportedError:
                raise
            except (TimeoutError, ValueError) as e:  # the end never came, or a garbled line
                problem = str(e) or type(e).__name__
                logger.warning(f"{who}: {what} attempt {attempt} of {attempts} failed: {problem}")
                continue
            except (ConnectionError, RuntimeError) as e:
                logger.warning(f"{who}: {what} failed: {e}")
                return None
            except Exception as e:
                logger.exception(f"{who}: {what} failed: {e}")
                return None

            if result.is_complete:
                logger.info(
                    f"{who}: read the {what}, {result.entries} (attempt {attempt} of {attempts})"
                )
                return result
            problem = f"{result.entries}, expected {type(result).EXPECTED_ENTRIES}"
            logger.warning(f"{who}: {what} attempt {attempt} of {attempts} incomplete: {problem}")

        logger.error(
            f"{who}: gave up on the {what} after {attempts} attempts ({problem}), not uploaded."
        )
        return None

    def _publish_diagnostic(self, diagnostic: UiCurve | PulseForm) -> None:
        """Hand a UI curve or pulse form to the diagnostics queue and the uploader.
        The upload itself runs on the manager thread with the snapshots."""
        if isinstance(self._diagnostics_queue, queue.Queue):
            self._diagnostics_queue.put(diagnostic)
        if self._upload_active:
            with self._diagnostics_lock:
                self._pending_diagnostics.append(diagnostic)
            self._wake_sender.set()

    def _loop_serial_manager(self) -> None:
        if self._manager_serial is not None and self._manager_serial.is_alive():
            self._upload_blocked_devices = self._manager_serial.get_settling_serial_numbers()
            self._data = add_to_existing_naneos_data(self._data, self._manager_serial.get_data())

        self._manager_serial = self._sync_manager(
            self._manager_serial,
            self._use_serial,
            lambda: PartectorSerialManager(
                self._serial_gain_test,
                self._serial_pulse_diagnostics,
                self._on_live_point,
                self._sample_rate_hz,
            ),
            "serial",
        )

    def _loop_ble_manager(self) -> None:
        if self._manager_ble is not None and self._manager_ble.is_alive():
            self._data = add_to_existing_naneos_data(self._data, self._manager_ble.get_data())

        self._manager_ble = self._sync_manager(
            self._manager_ble,
            self._use_ble,
            lambda: PartectorBleManager(
                self._ble_serial_numbers,
                self._ble_max_links,
                self._on_live_point,
                self._ble_p2pro_mode,
                self._ble_may_set_p2pro_mode,
            ),
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
                self._tick_diagnostics()

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
        """Hand a gathered snapshot to the output queue and the uploader.

        The upload never runs here: the snapshot goes into the backlog, and the
        sender thread takes it from there.
        """
        if isinstance(self._out_queue, queue.Queue):
            self._out_queue.put(snapshot)

        if not self._upload_active:
            return

        try:
            evicted = self._backlog.add(prepare_frames(snapshot))
        except Exception as e:  # a frame the upload cannot read must not stop the gathering
            logger.exception(f"Could not keep a snapshot for the upload: {e}")
            return
        self._log_eviction(evicted)
        self._wake_sender.set()

    def _sender_loop(self) -> None:
        """The thread that talks to the network, until the manager stops."""
        while not self._stop_event.is_set():
            try:
                done = self._drain_uploads()
            except Exception as e:
                logger.exception(f"Upload thread exception: {e}")
                done = False

            if done:
                self._retry_delay = 0
                if self._wake_sender.wait(timeout=1.0):
                    self._wake_sender.clear()
            else:
                delays = self.RETRY_DELAYS_SECONDS
                later = [delay for delay in delays if delay > self._retry_delay]
                self._retry_delay = later[0] if later else delays[-1]
                self._stop_event.wait(self._retry_delay)

    def _drain_uploads(self) -> bool:
        """Send what is waiting, oldest data first: the snapshots, then the diagnostics.

        The point timestamps are relative to the moment of sending, so data that
        waited for hours lands at its own time on the server. While the backlog is
        long, requests carry up to CHUNK_SECONDS of data.

        Returns False when a snapshot could not be sent and should be tried again
        later (it stays in the backlog), True otherwise.
        """
        if not self._upload_active:
            return True

        while not self._stop_event.is_set():
            chunk = self._backlog.take(self._chunk_seconds, self.MAX_CHUNK_ROWS)
            if chunk is None:
                break
            outcome = self._try_upload(chunk)
            if outcome in ("retry", "server"):
                self._snapshot_failed(chunk, outcome)
                return False
            self._snapshot_sent(chunk)

        self._drain_diagnostics()
        return True

    def _snapshot_failed(self, chunk: Chunk, outcome: str) -> None:
        self._log_eviction(self._backlog.restore(chunk))
        if self._outage_since is None:
            self._outage_since = time.time()

        smallest = self._gathering_interval_seconds
        if outcome == "server" and chunk.seconds > smallest:
            self._chunk_seconds = max(smallest, self._chunk_seconds // 2)
            logger.warning(
                f"The server refused a request, trying {self._chunk_seconds} s at a time."
            )
        logger.warning(
            f"Upload failed, keeping {self._backlog.snapshots} snapshot(s) "
            f"({self._backlog.size_bytes / 1e6:.1f} MB) for retry."
        )

    def _snapshot_sent(self, chunk: Chunk) -> None:
        if self._chunk_seconds < CHUNK_SECONDS:
            self._chunk_seconds = min(CHUNK_SECONDS, self._chunk_seconds * 2)
        if self._outage_since is not None:
            minutes = (time.time() - self._outage_since) / 60
            logger.info(
                f"Upload works again after {minutes:.0f} min, "
                f"{self._backlog.snapshots} snapshot(s) still to send."
            )
            self._outage_since = None

    def _drain_diagnostics(self) -> None:
        """Send the UI curves and pulse forms. A failing endpoint has a pause of its own,
        so that it does not delay the snapshots."""
        while not self._stop_event.is_set() and time.monotonic() >= self._diagnostics_retry_at:
            with self._diagnostics_lock:
                item = self._pending_diagnostics[0] if self._pending_diagnostics else None
            if item is None:
                return

            outcome = self._try_upload(item)
            if outcome in ("retry", "server"):
                delays = self.RETRY_DELAYS_SECONDS
                later = [d for d in delays if d > self._diagnostics_retry_delay]
                self._diagnostics_retry_delay = later[0] if later else delays[-1]
                self._diagnostics_retry_at = time.monotonic() + self._diagnostics_retry_delay
                logger.warning(
                    f"Upload failed, keeping {len(self._pending_diagnostics)} diagnostic(s) "
                    "for retry."
                )
                return

            self._diagnostics_retry_delay = 0
            with self._diagnostics_lock:
                if self._pending_diagnostics and self._pending_diagnostics[0] is item:
                    self._pending_diagnostics.popleft()

    def _log_eviction(self, evicted: Eviction | None) -> None:
        """Say that a full buffer dropped data, at most once a minute."""
        if evicted is None:
            return
        self._evicted = Eviction(
            self._evicted.snapshots + evicted.snapshots, self._evicted.seconds + evicted.seconds
        )
        now = time.monotonic()
        if self._evicted_logged_at is not None and now - self._evicted_logged_at < 60:
            return
        self._evicted_logged_at = now
        logger.warning(
            f"Upload buffer is full ({self._backlog.size_bytes / 1e6:.0f} MB): dropped the oldest "
            f"{self._evicted.snapshots} snapshot(s), about {self._evicted.seconds / 60:.0f} min "
            "of data."
        )
        self._evicted = Eviction(0, 0)

    @staticmethod
    def _try_upload(item: Chunk | UiCurve | PulseForm) -> str:
        """Returns "ok", "drop" (rejected), "retry" (no answer, the network) or "server"
        (an answer that says try again later, or none in time: the server is too slow for
        a request of this size)."""
        try:
            if isinstance(item, UiCurve | PulseForm):
                response = upload_diagnostic(item)
            else:
                response = send_frames(item.frames)
        except ReadTimeout as e:
            logger.warning(f"Upload timed out, the server did not answer: {e}")
            return "server"
        except Exception as e:
            logger.warning(f"Upload failed: {e}")
            return "retry"

        status, detail = backend_status(response)
        if 200 <= status < 300:
            logger.info(f"Uploaded {NaneosDeviceManager._describe(item)}")
            return "ok"
        if status >= 500 or status in (408, 429):
            logger.warning(f"Upload failed with HTTP {status} {detail}, will retry.")
            return "server"

        # A 4xx will not get better by resending the same payload, and a retry
        # would hold up everything queued behind it.
        what = NaneosDeviceManager._describe(item)
        wrapped = f" (inside HTTP {response.status_code})" if status != response.status_code else ""
        logger.error(f"Upload rejected with HTTP {status}{wrapped} {detail}, dropping {what}.")
        return "drop"

    @staticmethod
    def _describe(item: Chunk | UiCurve | PulseForm) -> str:
        """What a request carried, for the log: a burst of uploads should say what it is."""
        if isinstance(item, UiCurve | PulseForm):
            return f"{type(item).__name__} of SN{item.serial_number} ({item.entries})"
        merged = f", {item.snapshots} snapshots merged" if item.snapshots > 1 else ""
        return f"snapshot: {len(item.frames)} device(s), {item.rows} rows, {item.seconds} s{merged}"

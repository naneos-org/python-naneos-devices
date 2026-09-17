import asyncio
import sys
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd
from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from naneos.ble.connection import PartectorBleConnection
from naneos.ble.device import BlePartector
from naneos.ble.scanner import PartectorBleScanner
from naneos.data_point import NaneosDeviceDataPoint
from naneos.device import PartectorDevice
from naneos.frames import MAX_ROWS_PER_DEVICE, to_pandas_df
from naneos.logger import get_naneos_logger

logger = get_naneos_logger(__name__)


@dataclass
class BleLink:
    """Everything the manager knows about one device it decided to connect to."""

    task: asyncio.Task
    connection: PartectorBleConnection | None = None  # set while the task runs
    device: BlePartector | None = None  # the handle given to users, set with the connection

    @property
    def is_connected(self) -> bool:
        """True only while a GATT link is actually up, not while retrying."""
        return self.connection is not None and self.connection.is_connected


class PartectorBleManager(threading.Thread):
    """Connects to the Partectors in reach and collects the data they send over the link.

    Only connected devices deliver data. The scanner is used to find devices,
    to gate connects by signal strength and to refresh stale device handles.

    Args:
        serial_numbers: Only connect to these devices. None connects to every
            Partector in reach, first come first served.
        max_links: Upper bound of simultaneous links (including ones that are
            still retrying). BlueZ handles about seven reliably.
    """

    # How often the manager drains its queues. The queues are bounded and the
    # producers are ~1Hz per device, so polling faster only burns CPU on a
    # Raspberry Pi Zero 2 W without delivering data any sooner.
    LOOP_INTERVAL_SECONDS = 1.0

    # The adapter is considered lost after discovery has been down this long.
    # Discovery failing *is* the adapter check, so no subprocess is needed while
    # running; `bluetoothctl` is only used to decide when it is safe to restart.
    ADAPTER_LOST_AFTER_SECONDS = 30.0
    ADAPTER_CHECK_INTERVAL_SECONDS = 3.0

    # On a normal stop the links get this long to disconnect gracefully before
    # their tasks are cancelled.
    SHUTDOWN_GRACE_SECONDS = 8.0

    DEFAULT_MAX_LINKS = 7

    def __init__(
        self, serial_numbers: Iterable[int] | None = None, max_links: int = DEFAULT_MAX_LINKS
    ) -> None:
        super().__init__(daemon=True)
        self._allowed_serials: frozenset[int] | None = (
            frozenset(serial_numbers) if serial_numbers is not None else None
        )
        self._max_links = max(1, max_links)
        self._stop_event = threading.Event()
        # Ends the connection tasks of the current scanner session; only polled,
        # never awaited, so setting it from another thread is fine.
        self._task_stop_event = asyncio.Event()

        self._queue_scanner = PartectorBleScanner.create_scanner_queue()
        self._queue_connection = PartectorBleConnection.create_connection_queue()
        self._links: dict[int, BleLink] = {}  # key: serial number
        self._rejected_for_cap: set[int] = set()
        self._scanner: PartectorBleScanner | None = None

        # Raw data points from the links, converted to DataFrames only in
        # get_data(). Building them here would put pandas on the event loop that
        # also services the BLE notifications, which on a Raspberry Pi Zero 2 W is
        # enough to stall the links themselves.
        self._points: dict[int, list[NaneosDeviceDataPoint]] = {}

    # == Public API (any thread) ===================================================================
    def get_data(self) -> dict[int, pd.DataFrame]:
        """Returns the collected data as DataFrames and clears the buffer."""
        # Swap first: the BLE thread keeps appending while we convert.
        points, self._points = self._points, {}

        return {
            serial: df
            for serial, serial_points in points.items()
            if not (df := to_pandas_df(serial_points)).empty
        }

    def stop(self) -> None:
        self._task_stop_event.set()
        self._stop_event.set()

    def run(self) -> None:
        try:
            asyncio.run(self._async_run())
        except RuntimeError as e:
            logger.exception(f"BLEManager loop exited with: {e}")

    def get_connected_serial_numbers(self) -> list[int]:
        """Serial numbers of the devices with a live BLE link."""
        return [sn for sn, _ in self._live_links()]

    def get_devices(self) -> list[PartectorDevice]:
        """Handles to write to and query the devices with a live BLE link."""
        return [link.device for _, link in self._live_links() if link.device is not None]

    def _live_links(self) -> list[tuple[int, BleLink]]:
        # Copy first: the event loop thread changes the dict while we iterate.
        return [(sn, link) for sn, link in list(self._links.items()) if link.is_connected]

    # == Event loop ================================================================================
    async def _async_run(self) -> None:
        self._loop = asyncio.get_running_loop()

        while not self._stop_event.is_set():
            await self._wait_for_bluetooth_adapter()
            if self._stop_event.is_set():
                break

            self._task_stop_event.clear()
            self._scanner = PartectorBleScanner(loop=self._loop, queue=self._queue_scanner)
            adapter_lost = False
            try:
                async with self._scanner:
                    logger.info("Scanner started.")
                    adapter_lost = await self._manager_loop()
            except asyncio.CancelledError:
                logger.info("BLEManager cancelled.")
                break
            finally:
                # A lost adapter cannot disconnect anything gracefully anyway.
                grace = 0.0 if adapter_lost else self.SHUTDOWN_GRACE_SECONDS
                await self._shutdown_links(grace_seconds=grace)
                logger.info("BLEManager cleanup complete.")

    async def _manager_loop(self) -> bool:
        """Runs until stopped. Returns True if it ended because the adapter was lost."""
        discovery_down_since: float | None = None

        while not self._stop_event.is_set():
            try:
                # The scanner reports whether BlueZ discovery is actually running.
                # Probing the adapter with a `bluetoothctl` subprocess instead cost
                # a fork/exec plus a D-Bus round trip against the same bluetoothd
                # that carries the BLE links.
                if self._scanner is not None and not self._scanner.is_discovering:
                    now = time.monotonic()
                    if discovery_down_since is None:
                        discovery_down_since = now
                    elif now - discovery_down_since >= self.ADAPTER_LOST_AFTER_SECONDS:
                        logger.warning("Bluetooth adapter lost. Stopping all connections...")
                        return True
                else:
                    discovery_down_since = None

                await asyncio.sleep(self.LOOP_INTERVAL_SECONDS)

                await self._scanner_queue_routine()
                await self._connection_queue_routine()
                self._forget_finished_links()

            except Exception as e:
                logger.exception(f"Error in manager loop: {e}")

        return False

    async def _shutdown_links(self, grace_seconds: float) -> None:
        """Ends every connection task: first by asking, then by cancelling."""
        self._task_stop_event.set()

        pending = [link.task for link in self._links.values() if not link.task.done()]
        if pending and grace_seconds > 0:
            _, still_pending = await asyncio.wait(pending, timeout=grace_seconds)
            pending = list(still_pending)
            if pending:
                # Normal for a link that is inside a connect attempt to an
                # unreachable device: connect() can take up to its own timeout.
                logger.info(f"{len(pending)} connection task(s) still busy, cancelling.")

        for task in pending:
            task.cancel()
        if pending:
            await asyncio.wait(pending, timeout=2.0)  # let the cancellation propagate

        self._links.clear()

    async def _task_connection(self, device: BLEDevice, serial: int) -> None:
        connection = PartectorBleConnection(
            device=device,
            loop=self._loop,
            serial_number=serial,
            queue=self._queue_connection,
            rssi_provider=lambda: self._get_rssi(device.address),
            device_provider=lambda: self._get_device(device.address),
        )
        link = self._links.get(serial)
        if link is not None:
            link.connection = connection
            link.device = BlePartector(connection, self._loop)

        try:
            async with connection:
                while not self._task_stop_event.is_set():
                    await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info(f"{serial}: Connection task cancelled.")
        except Exception as e:
            logger.warning(f"{serial}: Connection task failed: {e}")
        finally:
            if link is not None:
                link.connection = None
                link.device = None
            logger.info(f"{serial}: Connection task finished.")

    def _forget_finished_links(self) -> None:
        for serial, link in list(self._links.items()):
            if link.task.done():
                self._links.pop(serial, None)
                logger.info(f"{serial}: Connection task finished and popped.")

    # == Adapter ===================================================================================
    async def _wait_for_bluetooth_adapter(self) -> None:
        while not self._stop_event.is_set():
            if await self._adapter_available():
                logger.info("Bluetooth adapter is available and ready.")
                return

            logger.info(
                "Bluetooth adapter not available. "
                f"Retrying in {self.ADAPTER_CHECK_INTERVAL_SECONDS} seconds..."
            )
            await asyncio.sleep(self.ADAPTER_CHECK_INTERVAL_SECONDS)

    @staticmethod
    async def _adapter_available() -> bool:
        """Is there a powered Bluetooth adapter to start a scanner session on?"""
        if sys.platform.startswith("linux"):
            return await _bluez_adapter_powered()

        try:
            scanner = BleakScanner()
            await scanner.start()
            await scanner.stop()
            return True
        except Exception as e:
            logger.debug(f"Bluetooth adapter not available: {e}")
            return False

    # == Queue draining ============================================================================
    def _get_device(self, address: str) -> BLEDevice | None:
        """Most recently advertised BLEDevice for an address, or None."""
        if self._scanner is None:
            return None
        return self._scanner.get_device(address)

    def _get_rssi(self, address: str) -> int | None:
        """Most recent RSSI for an address, or None if it is stale / unknown."""
        if self._scanner is None:
            return None
        return self._scanner.get_rssi(address)

    def _buffer_points(self, points: list[NaneosDeviceDataPoint]) -> None:
        """Append data points to the per-device buffer, keeping the newest ones."""
        for point in points:
            if point.serial_number is None:
                continue
            buffered = self._points.setdefault(point.serial_number, [])
            buffered.append(point)
            if len(buffered) > MAX_ROWS_PER_DEVICE:
                del buffered[:-MAX_ROWS_PER_DEVICE]

    async def _scanner_queue_routine(self) -> None:
        """Drain the scanner queue and start a link for every new device that qualifies."""
        seen: dict[int, BLEDevice] = {}

        while not self._queue_scanner.empty():
            try:
                device, serial = self._queue_scanner.get_nowait()
            except asyncio.QueueEmpty:
                break
            seen[serial] = device

        for serial, device in seen.items():
            if serial in self._links:
                continue
            if not self._wants_link(serial):
                continue

            rssi = self._get_rssi(device.address)
            if rssi is not None and rssi < PartectorBleConnection.MIN_RSSI_CONNECT_DBM:
                logger.info(
                    f"Ignoring serial={serial} ({device.address}): RSSI {rssi} dBm is below "
                    f"{PartectorBleConnection.MIN_RSSI_CONNECT_DBM} dBm."
                )
                continue

            logger.info(
                f"New device detected: serial={serial}, address={device.address}, rssi={rssi}"
            )
            task = self._loop.create_task(self._task_connection(device, serial))
            self._links[serial] = BleLink(task=task)

    def _wants_link(self, serial: int) -> bool:
        """Allow-list and link cap. Logged once per device per decision, not per second."""
        if self._allowed_serials is not None and serial not in self._allowed_serials:
            return False
        if len(self._links) >= self._max_links:
            if serial not in self._rejected_for_cap:
                logger.info(f"Not connecting to serial={serial}: {self._max_links} links in use.")
                self._rejected_for_cap.add(serial)
            return False
        self._rejected_for_cap.discard(serial)
        return True

    async def _connection_queue_routine(self) -> None:
        """Drain the connection queue and record the data points in one batch."""
        batch_data: list[NaneosDeviceDataPoint] = []

        while not self._queue_connection.empty():
            try:
                batch_data.append(self._queue_connection.get_nowait())
            except asyncio.QueueEmpty:
                break

        self._buffer_points(batch_data)


async def _bluez_adapter_powered() -> bool:
    """Asks BlueZ (`bluetoothctl show`) whether a controller exists and is powered on."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl",
            "show",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
    except FileNotFoundError:
        logger.debug("bluetoothctl not found on system.")
        return False
    except Exception as e:
        logger.debug(f"Error while checking Bluetooth adapter via bluetoothctl: {e}")
        return False

    if proc.returncode != 0:
        logger.debug(
            f"bluetoothctl show failed with code {proc.returncode}: "
            f"{stderr.decode(errors='ignore').strip()}"
        )
        return False

    output = stdout.decode(errors="ignore")
    if "No default controller available" in output:
        logger.debug("No default Bluetooth controller available (BlueZ).")
        return False

    for line in output.splitlines():
        if line.strip().lower().startswith("powered:"):
            return "yes" in line.lower()

    logger.debug("Bluetooth controller found but no 'Powered' field in output.")
    return False

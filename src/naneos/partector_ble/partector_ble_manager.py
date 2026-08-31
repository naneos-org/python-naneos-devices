import asyncio
import sys
import threading
import time

import pandas as pd
from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from naneos.logger import LEVEL_WARNING, get_naneos_logger
from naneos.partector.blueprints._data_structure import (
    NaneosDeviceDataPoint,
)
from naneos.partector_ble.partector_ble_connection import PartectorBleConnection
from naneos.partector_ble.partector_ble_scanner import PartectorBleScanner

pd.set_option("future.no_silent_downcasting", True)

logger = get_naneos_logger(__name__, LEVEL_WARNING)


class PartectorBleManager(threading.Thread):
    # How often the manager drains its queues. The queues are bounded and the
    # producers are ~1Hz per device, so polling faster only burns CPU on a
    # Raspberry Pi Zero 2 W without delivering data any sooner.
    LOOP_INTERVAL_SECONDS = 1.0

    # The adapter is considered lost after discovery has been down this long.
    # Discovery failing *is* the adapter check, so no subprocess is needed while
    # running; `bluetoothctl` is only used to decide when it is safe to restart.
    ADAPTER_LOST_AFTER_SECONDS = 30.0

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self._task_stop_event = asyncio.Event()

        self._queue_scanner = PartectorBleScanner.create_scanner_queue()
        self._queue_connection = PartectorBleConnection.create_connection_queue()
        self._connections: dict[int, tuple[asyncio.Task, int]] = {}  # key: serial_number
        # live connection objects, so we can report the real link state
        self._connection_objects: dict[int, PartectorBleConnection] = {}
        self._scanner: PartectorBleScanner | None = None

        # Raw data points, converted to DataFrames only in get_data(). Building
        # them here would put pandas on the event loop that also services the BLE
        # notifications, which on a Raspberry Pi Zero 2 W is enough to stall the
        # links themselves.
        self._points: dict[int, list[NaneosDeviceDataPoint]] = {}

    def get_data(self) -> dict[int, pd.DataFrame]:
        """Returns the collected data as DataFrames and clears the buffer."""
        # Swap first: the BLE thread keeps appending while we convert.
        points, self._points = self._points, {}

        return {
            serial: df
            for serial, serial_points in points.items()
            if not (df := NaneosDeviceDataPoint.to_pandas_df(serial_points)).empty
        }

    def _buffer_points(self, points: list[NaneosDeviceDataPoint]) -> None:
        """Append data points to the per-device buffer, keeping the newest ones."""
        for point in points:
            buffered = self._points.setdefault(point.serial_number, [])
            buffered.append(point)
            if len(buffered) > NaneosDeviceDataPoint.MAX_ROWS_PER_DEVICE:
                del buffered[: -NaneosDeviceDataPoint.MAX_ROWS_PER_DEVICE]

    def stop(self) -> None:
        self._task_stop_event.set()
        self._stop_event.set()

    def run(self) -> None:
        try:
            asyncio.run(self._async_run())
        except RuntimeError as e:
            logger.exception(f"BLEManager loop exited with: {e}")

    def get_connected_device_strings(self) -> list[str]:
        """Returns a list of device strings for devices with a live BLE link.

        Devices that are only being retried (task exists, but no GATT connection)
        are deliberately not reported here.
        """
        # first make a copy to avoid runtime dict change issues
        connections_copy = self._connections.copy()
        objects_copy = self._connection_objects.copy()

        sns = [
            sn for sn in connections_copy if sn in objects_copy and objects_copy[sn].is_connected
        ]
        device_types = [connections_copy[s][1] for s in sns]

        sns_list = []
        for sn, dev_type in zip(sns, device_types):
            if dev_type == NaneosDeviceDataPoint.DEV_TYPE_P2PRO:
                sns_list.append(f"SN{sn} (P2 Pro)")
        for sn, dev_type in zip(sns, device_types):
            if dev_type == NaneosDeviceDataPoint.DEV_TYPE_P2:
                sns_list.append(f"SN{sn} (P2)")

        return sns_list

    def get_connected_serial_numbers(self) -> list[int | None]:
        """Returns a list of connected serial numbers."""
        return list(self._connections.keys())

    async def _bleak_is_bluetooth_adapter_available(self) -> bool:
        """Check if the Bluetooth adapter is available and powered on."""
        try:
            # Try to get adapter info - this will fail if adapter is not available
            scanner = BleakScanner()
            # Test if we can discover devices briefly
            await scanner.start()
            await scanner.stop()
            return True
        except Exception as e:
            logger.debug(f"Bluetooth adapter not available: {e}")
            return False

    async def _linux_is_bluetooth_adapter_available(self) -> bool:
        """
        Nutzt BlueZ (bluetoothctl show), um zu prüfen, ob
        - ein Bluetooth-Controller existiert und
        - er eingeschaltet ("Powered: yes") ist.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "bluetoothctl",
                "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.debug(
                    "bluetoothctl show failed with code %s: %s",
                    proc.returncode,
                    stderr.decode(errors="ignore").strip(),
                )
                return False

            output = stdout.decode(errors="ignore")

            if "No default controller available" in output:
                logger.debug("No default Bluetooth controller available (BlueZ).")
                return False

            powered = None
            for line in output.splitlines():
                line = line.strip()
                if line.lower().startswith("powered:"):
                    powered = "yes" in line.lower()
                    break

            if powered is not None:
                return powered

            logger.debug("Bluetooth controller found but no 'Powered' field in output.")
            return False

        except FileNotFoundError:
            logger.debug("bluetoothctl not found on system.")
            return False

        except Exception as e:
            logger.debug(f"Error while checking Bluetooth adapter via bluetoothctl: {e}")
            return False

    async def _is_bluetooth_adapter_available(self) -> bool:
        if sys.platform.startswith("linux"):
            return await self._linux_is_bluetooth_adapter_available()
        else:
            return await self._bleak_is_bluetooth_adapter_available()

    async def _wait_for_bluetooth_adapter(self) -> None:
        """Wait for the Bluetooth adapter to become available."""
        adapter_check_interval = 3.0  # seconds

        while not self._stop_event.is_set():
            if await self._is_bluetooth_adapter_available():
                logger.info("Bluetooth adapter is available and ready.")
                return

            logger.info(
                f"Bluetooth adapter not available. Retrying in {adapter_check_interval} seconds..."
            )
            await asyncio.sleep(adapter_check_interval)

    async def _async_run(self):
        self._loop = asyncio.get_event_loop()
        while not self._stop_event.is_set():
            try:
                # Wait for Bluetooth adapter to become available
                await self._wait_for_bluetooth_adapter()
                self._task_stop_event.clear()

                self._scanner = PartectorBleScanner(loop=self._loop, queue=self._queue_scanner)
                async with self._scanner:
                    logger.info("Scanner started.")
                    await self._manager_loop()
                await self._kill_all_connections()  # just to be safe
            except asyncio.CancelledError:
                logger.info("BLEManager cancelled.")
            finally:
                logger.info("BLEManager cleanup complete.")

    async def _manager_loop(self) -> None:
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
                        await self._kill_all_connections()
                        return
                else:
                    discovery_down_since = None

                await asyncio.sleep(self.LOOP_INTERVAL_SECONDS)

                await self._scanner_queue_routine()
                await self._connection_queue_routine()
                await self._remove_done_tasks()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.exception(f"Error in manager loop: {e}")

        await self._finish_all_connections()

    async def _kill_all_connections(self) -> None:
        self._task_stop_event.set()

        for serial in list(self._connections.keys()):
            if not self._connections[serial][0].done():
                logger.info(f"Cancelling connection task {serial}.")
                self._connections[serial][0].cancel()
            self._connections.pop(serial, None)
            self._connection_objects.pop(serial, None)
            logger.info(f"{serial}: Connection task cancelled and popped.")

    async def _finish_all_connections_blocking(self) -> None:
        while list(self._connections.keys()):
            serial = list(self._connections.keys())[0]

            if not self._connections[serial][0].done():
                await asyncio.sleep(1)
            else:
                self._connections.pop(serial, None)

    async def _finish_all_connections(self) -> None:
        self._task_stop_event.set()
        await asyncio.sleep(1)  # give tasks some time to finish gracefully

        # wait max 5s for _finish_all_connections_blocking to finish
        try:
            await asyncio.wait_for(self._finish_all_connections_blocking(), timeout=7)
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for connections to finish. Forcing cancellation.")

        for serial in list(self._connections.keys()):
            if not self._connections[serial][0].done():
                logger.warning(f"Forcing connection task {serial} to cancel.")
                self._connections[serial][0].cancel()
                await asyncio.sleep(0.1)  # small delay to allow cancellation to propagate
                # logger.info(f"Waiting for connection task {serial} to finish.")
                # await self._connections[serial]

            self._connections.pop(serial, None)
            logger.info(f"{serial}: Connection task finished and popped.")

    async def _task_connection(self, device: BLEDevice, serial: int) -> None:
        connection = PartectorBleConnection(
            device=device,
            loop=self._loop,
            serial_number=serial,
            queue=self._queue_connection,
            rssi_provider=lambda: self._get_rssi(device.address),
            device_provider=lambda: self._get_device(device.address),
        )
        self._connection_objects[serial] = connection

        try:
            async with connection:
                while not self._task_stop_event.is_set():
                    await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info(f"{serial}: Connection task cancelled.")
        except Exception as e:
            logger.warning(f"{serial}: Connection task failed: {e}")
        finally:
            self._connection_objects.pop(serial, None)
            logger.info(f"{serial}: Connection task finished.")

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

    async def _scanner_queue_routine(self) -> None:
        """Drain the scanner queue and record the advertisements in one batch."""
        to_check: dict[int, BLEDevice] = {}
        batch_data: list[NaneosDeviceDataPoint] = []

        # Collect all available items from queue (non-blocking batch)
        while not self._queue_scanner.empty():
            try:
                device, decoded = self._queue_scanner.get_nowait()
            except asyncio.QueueEmpty:
                break

            if not decoded.serial_number:
                continue

            batch_data.append(decoded)
            to_check[decoded.serial_number] = device

        # Advertisement timestamps are truncated to whole seconds and
        # sort_and_clean_naneos_data() keeps only the last row per timestamp, so
        # everything but the newest advertisement per device-second is built into
        # a DataFrame just to be thrown away again downstream.
        deduped = {(d.serial_number, d.unix_timestamp): d for d in batch_data}

        self._buffer_points(list(deduped.values()))

        # check for new devices
        for serial, device in to_check.items():
            if serial in self._connections:
                continue  # already connected

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
            self._connections[serial] = (task, NaneosDeviceDataPoint.DEV_TYPE_P2)

    async def _connection_queue_routine(self) -> None:
        """Drain the connection queue and record the data points in one batch."""
        batch_data: list[NaneosDeviceDataPoint] = []

        # Collect all available items from queue (non-blocking batch)
        while not self._queue_connection.empty():
            try:
                data = self._queue_connection.get_nowait()
            except asyncio.QueueEmpty:
                break

            batch_data.append(data)

        # A connected device reveals whether it is a P2 or a P2 Pro through the
        # points it sends. Reading that back out of the DataFrame (.iloc[-1]) on
        # every loop iteration was pure overhead; take it from the batch instead.
        for data in batch_data:
            entry = self._connections.get(data.serial_number)
            if entry is not None and data.device_type is not None and entry[1] != data.device_type:
                self._connections[data.serial_number] = (entry[0], data.device_type)

        self._buffer_points(batch_data)

    async def _remove_done_tasks(self) -> None:
        """Remove completed tasks from the connections dictionary."""
        for serial in list(self._connections.keys()):
            if self._connections[serial][0].done():
                self._connections.pop(serial, None)
                logger.info(f"{serial}: Connection task finished and popped.")


if __name__ == "__main__":
    manager = PartectorBleManager()
    manager.start()

    for _ in range(2):
        time.sleep(10)  # Allow some time for the scanner to start
        data = manager.get_data()

        print(f"Connected serial numbers: {manager.get_connected_serial_numbers()}")
        print("Collected data:")
        print()

        for sn, df in data.items():
            print(f"SN: {sn}")
            print(df)
            print("-" * 40)
            print()

    manager.stop()
    manager.join()

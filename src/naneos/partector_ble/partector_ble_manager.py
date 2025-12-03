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
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self._task_stop_event = asyncio.Event()

        self._queue_scanner = PartectorBleScanner.create_scanner_queue()
        self._queue_connection = PartectorBleConnection.create_connection_queue()
        self._connections: dict[int, tuple[asyncio.Task, int]] = {}  # key: serial_number

        self._data: dict[int, pd.DataFrame] = {}

    def get_data(self) -> dict[int, pd.DataFrame]:
        """Returns the data dictionary and deletes it."""
        data = self._data
        self._data = {}
        return data

    def stop(self) -> None:
        self._task_stop_event.set()
        self._stop_event.set()

    def run(self) -> None:
        try:
            asyncio.run(self._async_run())
        except RuntimeError as e:
            logger.exception(f"BLEManager loop exited with: {e}")

    def get_connected_device_strings(self) -> list[str]:
        """Returns a list of connected device strings."""
        # first make a copy to avoid runtime dict change issues
        connections_copy = self._connections.copy()
        sns = connections_copy.keys()
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

                async with PartectorBleScanner(loop=self._loop, queue=self._queue_scanner):
                    logger.info("Scanner started.")
                    await self._manager_loop()
                await self._kill_all_connections()  # just to be safe
            except asyncio.CancelledError:
                logger.info("BLEManager cancelled.")
            finally:
                logger.info("BLEManager cleanup complete.")

    async def _manager_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if not await self._is_bluetooth_adapter_available():
                    logger.warning("Bluetooth adapter lost. Stopping all connections...")
                    await self._kill_all_connections()
                    return

                await asyncio.sleep(1.0)

                await self._scanner_queue_routine()
                await self._connection_queue_routine()
                await self._check_device_types()
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
        try:
            async with PartectorBleConnection(
                device=device, loop=self._loop, serial_number=serial, queue=self._queue_connection
            ):
                while not self._task_stop_event.is_set():
                    await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            logger.info(f"{serial}: Connection task cancelled.")
        except Exception as e:
            logger.warning(f"{serial}: Connection task failed: {e}")
        finally:
            logger.info(f"{serial}: Connection task finished.")

    async def _scanner_queue_routine(self) -> None:
        to_check: dict[int, BLEDevice] = {}

        while not self._queue_scanner.empty():
            device, decoded = await self._queue_scanner.get()
            if not decoded.serial_number:
                continue

            self._data = NaneosDeviceDataPoint.add_data_point_to_dict(self._data, decoded)
            to_check[decoded.serial_number] = device

        # check for new devices
        for serial, device in to_check.items():
            if serial in self._connections:
                continue  # already connected

            logger.info(f"New device detected: serial={serial}, address={device.address}")
            task = self._loop.create_task(self._task_connection(device, serial))
            self._connections[serial] = (task, NaneosDeviceDataPoint.DEV_TYPE_P2)

    async def _connection_queue_routine(self) -> None:
        while not self._queue_connection.empty():
            data = await self._queue_connection.get()
            self._data = NaneosDeviceDataPoint.add_data_point_to_dict(self._data, data)

    async def _check_device_types(self) -> None:
        for serial in self._data.keys():
            if serial not in self._connections:
                continue

            current_type = self._connections[serial][1]
            data_points = self._data[serial]

            # get last value of device_type column
            if data_points.empty:
                continue
            last_device_type = data_points["device_type"].iloc[-1]
            if last_device_type != current_type:
                self._connections[serial] = (
                    self._connections[serial][0],
                    last_device_type,
                )

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

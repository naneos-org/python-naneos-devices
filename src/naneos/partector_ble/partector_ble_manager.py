import asyncio
import threading
import time
from typing import Dict

import pandas as pd
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

        self._queue_scanner = PartectorBleScanner.create_scanner_queue()
        self._queue_connection = PartectorBleConnection.create_connection_queue()
        self._connections: Dict[int, asyncio.Task] = {}  # key: serial_number

        self._data: dict[int, pd.DataFrame] = {}

    def get_data(self) -> dict[int, pd.DataFrame]:
        """Returns the data dictionary and deletes it."""
        data = self._data
        self._data = {}
        return data

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            asyncio.run(self._async_run())
        except RuntimeError as e:
            logger.exception(f"BLEManager loop exited with: {e}")

    def get_connected_device_strings(self) -> list[str]:
        """Returns a list of connected device strings."""
        return [f"SN{sn}" for sn in self._connections.keys()]

    def get_connected_serial_numbers(self) -> list[int | None]:
        """Returns a list of connected serial numbers."""
        return list(self._connections.keys())

    async def _async_run(self):
        self._loop = asyncio.get_event_loop()
        try:
            async with PartectorBleScanner(loop=self._loop, queue=self._queue_scanner):
                logger.info("Scanner started.")
                await self._manager_loop()
        except asyncio.CancelledError:
            logger.info("BLEManager cancelled.")
        finally:
            logger.info("BLEManager cleanup complete.")

    async def _manager_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(1.0)

                await self._scanner_queue_routine()
                await self._connection_queue_routine()
                await self._remove_done_tasks()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.exception(f"Error in scanner loop: {e}")

        # wait for all connections to finish
        for serial in list(self._connections.keys()):
            if not self._connections[serial].done():
                logger.info(f"Waiting for connection task {serial} to finish.")
                await self._connections[serial]
            self._connections.pop(serial, None)
            logger.info(f"{serial}: Connection task finished and popped.")

    async def _task_connection(self, device: BLEDevice, serial: int) -> None:
        try:
            async with PartectorBleConnection(
                device=device, loop=self._loop, serial_number=serial, queue=self._queue_connection
            ):
                while not self._stop_event.is_set():
                    await asyncio.sleep(1)

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
            self._connections[serial] = task

    async def _connection_queue_routine(self) -> None:
        while not self._queue_connection.empty():
            data = await self._queue_connection.get()
            self._data = NaneosDeviceDataPoint.add_data_point_to_dict(self._data, data)

    async def _remove_done_tasks(self) -> None:
        """Remove completed tasks from the connections dictionary."""
        for serial in list(self._connections.keys()):
            if self._connections[serial].done():
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

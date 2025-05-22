import asyncio
import threading
import time
from typing import Dict

from bleak.backends.device import BLEDevice

from naneos.logger import LEVEL_INFO, get_naneos_logger
from naneos.partector.blueprints._data_structure import Partector2DataStructure
from naneos.partector_ble.decoder.partector_ble_decoder_aux import PartectorBleDecoderAux
from naneos.partector_ble.decoder.partector_ble_decoder_std import PartectorBleDecoderStd
from naneos.partector_ble.partector_ble_connection import PartectorBleConnection
from naneos.partector_ble.partector_ble_scanner import PartectorBleScanner

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleManager(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop_event = threading.Event()

        self._queue_scanner = PartectorBleScanner.create_scanner_queue()
        self._queue_connection = PartectorBleConnection.create_connection_queue()
        self._connections: Dict[int, asyncio.Task] = {}  # key: serial_number

        self._list_scanner: list[Partector2DataStructure] = []
        self._list_connection: list[Partector2DataStructure] = []

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            asyncio.run(self._async_run())
        except RuntimeError as e:
            logger.exception(f"BLEManager loop exited with: {e}")

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

        except Exception as e:
            logger.warning(f"{serial}: Connection task failed: {e}")
        finally:
            logger.info(f"{serial}: Connection task finished.")

    async def _scanner_queue_routine(self) -> None:
        to_check: dict[int, BLEDevice] = {}

        while not self._queue_scanner.empty():
            device, adv_data = await self._queue_scanner.get()

            decoded = PartectorBleDecoderStd.decode(adv_data[0], data_structure=None)
            if adv_data[1]:
                decoded = PartectorBleDecoderAux.decode(adv_data[1], data_structure=decoded)
            decoded.unix_timestamp = int(time.time() * 1000)
            if not decoded.serial_number:
                continue

            if len(self._list_scanner) > 300:
                self._list_scanner.pop(0)
            self._list_scanner.append(decoded)

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
            logger.info(f"Data from device {data.serial_number}: {data}")


if __name__ == "__main__":
    manager = PartectorBleManager()
    manager.start()

    time.sleep(10)  # Allow some time for the scanner to start
    manager.stop()
    manager.join()

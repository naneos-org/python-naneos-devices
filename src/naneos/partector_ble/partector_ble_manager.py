import asyncio
import threading
from typing import Dict

from bleak.backends.device import BLEDevice

from naneos.logger import LEVEL_INFO, get_naneos_logger
from naneos.partector_ble.decoder.partector_ble_decoder_std import PartectorBleDecoderStd
from naneos.partector_ble.partector_ble_connection import PartectorBleConnection
from naneos.partector_ble.partector_ble_scanner import PartectorBleScanner

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleManager(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._connections: Dict[int, asyncio.Task] = {}  # key: serial_number
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            asyncio.run(self._main())
        except RuntimeError as e:
            logger.exception(f"BLEManager loop exited with: {e}")

    async def _main(self):
        self._loop = asyncio.get_event_loop()
        try:
            async with PartectorBleScanner(loop=self._loop, queue=self._queue):
                logger.info("Scanner started.")
                await self._scanner_loop()
        except asyncio.CancelledError:
            logger.info("BLEManager cancelled.")
        finally:
            # Optional: connections abbrechen
            logger.info("BLEManager cleanup complete.")

    async def _scanner_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                device, adv_data = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                decoded = PartectorBleDecoderStd.decode(adv_data[0], data_structure=None)
                serial = decoded.serial_number
                if not serial or serial in self._connections:
                    continue

                logger.info(f"New device detected: serial={serial}, address={device.address}")
                task = self._loop.create_task(self._handle_connection(device, serial))
                self._connections[serial] = task

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.exception(f"Error in scanner loop: {e}")

        logger.info("Scanner loop stopped.")

    async def _handle_connection(self, device: BLEDevice, serial: int) -> None:
        try:
            async with PartectorBleConnection(device=device, loop=self._loop, serial=serial):
                logger.info(f"Connected to device {serial}")
                while not self._stop_event.is_set():
                    await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Connection to {serial} failed: {e}")
        finally:
            logger.info(f"Disconnected from device {serial}")
            self._connections.pop(serial, None)


if __name__ == "__main__":
    import time

    manager = PartectorBleManager()
    manager.start()

    time.sleep(10)  # Allow some time for the scanner to start
    manager.stop()
    manager.join()

    # try:
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     print("Stopping BLEManager...")
    #     manager.stop()
    #     manager.join()

import asyncio
import threading
import time

from naneos.logger import LEVEL_INFO, get_naneos_logger
from naneos.partector_ble.partector_ble_scanner import PartectorBleScanner

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleManager(threading.Thread):
    """
    Partector BLE Manager class to handle BLE operations.
    """

    def __init__(self) -> None:
        super().__init__()
        self._stop_event = threading.Event()

        self._async_loop = asyncio.new_event_loop()

        self._async_scanner_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)
        self._async_scanner = PartectorBleScanner(
            loop=self._async_loop,
            auto_start=True,
            queue=self._async_scanner_queue,
        )

        self.start()

    def stop(self) -> None:
        """
        Stop the BLE manager and blocks until it is stopped.
        """
        self._stop_event.set()
        self.join()

    async def async_run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(0.5)  # Sleep to prevent busy waiting
                while not self._async_scanner_queue.empty():
                    data = await self._async_scanner_queue.get()
                    logger.info(f"Received data: {data!r}")
            except Exception as e:
                print(f"Error processing data: {e}")

    def run(self) -> None:
        """
        Run the BLE manager.
        """
        try:
            self._async_loop.run_until_complete(self.async_run())
        except Exception as e:
            logger.error(f"Error in BLE manager: {e}")
        finally:
            self._async_scanner.stop()


if __name__ == "__main__":
    ble_manager = PartectorBleManager()
    time.sleep(5)  # Let it run for a while
    ble_manager.stop()

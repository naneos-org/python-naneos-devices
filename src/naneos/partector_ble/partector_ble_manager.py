from __future__ import annotations

import asyncio
import threading
import time

from naneos.logger import LEVEL_INFO, get_naneos_logger
from naneos.partector_ble.partector_ble_scanner import PartectorBleScanner

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleManager(threading.Thread):
    """
    PartectorBleManager manages the full BLE process to our devices and runs in a separate thread.
    It uses the Bleak library to scan for BLE devices and processes the scan data asynchronously.
    """

    SCANNER_QUEUE_SIZE = 100

    def __init__(self) -> None:
        super().__init__()

        self._stop_event = threading.Event()

        # Create a new asyncio event loop for this thread, because bleak uses asyncio
        self._async_loop = asyncio.new_event_loop()

        self._async_scanner_queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=self.SCANNER_QUEUE_SIZE
        )
        self._async_scanner: PartectorBleScanner = PartectorBleScanner(
            loop=self._async_loop,
            auto_start=True,
            queue=self._async_scanner_queue,
        )

        self.start()

    def __del__(self) -> None:
        try:
            if not self._stop_event.is_set():
                self.stop()
        except Exception:
            pass  # Avoid raising exceptions during garbage collection

    def __enter__(self) -> PartectorBleManager:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    def stop(self) -> None:
        """
        Stop the BLE manager and blocks until it is stopped.
        """
        self._stop_event.set()
        self.join()
        logger.debug("PartectorBleManager stopped.")

    async def async_process_scan_data(self, scan: bytes) -> None:
        """
        Process the scan data asynchronously.

        Args:
            scan (bytes): The scan data to process.
        """
        logger.info(f"Processing scan data: {scan!r}")

    async def async_run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(0.5)  # Sleep to prevent busy waiting

                # Process the async scanner queue
                while not self._async_scanner_queue.empty():
                    scan = await self._async_scanner_queue.get()
                    await self.async_process_scan_data(scan)

            except Exception as e:
                logger.exception(e)

        # stopping the async objects that need a clean shutdown
        await self._async_scanner.stop()

    def run(self) -> None:
        """
        Runs the asyncio event loop and processes BLE scan data until the stop event is set.
        """
        try:
            self._async_loop.run_until_complete(self.async_run())
        except Exception as e:
            logger.exception(e)
        finally:
            if not self._async_loop.is_closed():
                self._async_loop.stop()
                self._async_loop.close()


if __name__ == "__main__":
    # old way of using the manager
    # ble_manager = PartectorBleManager()
    # time.sleep(5)  # Let it run for a while
    # ble_manager.stop()

    # usage with context manager
    with PartectorBleManager() as manager:
        time.sleep(5)  # Let it run for a while
        # The manager will automatically stop when exiting the context

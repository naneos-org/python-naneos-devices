from __future__ import annotations

import asyncio

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from naneos.logger import LEVEL_INFO, get_naneos_logger
from naneos.partector_ble.partector_ble_decoder import PartectorBleDecoder

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleScanner:
    """
    Context-managed BLE scanner for Partector devices.

    This scanner runs in the provided asyncio event loop and collects advertisement data
    from BLE devices named "P2" or "PartectorBT". Decoded advertisement payloads are
    pushed into an asyncio.Queue for further processing. Can be used with `async with`
    for automatic startup and cleanup.
    """

    BLE_NAMES_NANEOS = {"P2", "PartectorBT"}  # P2 on windows, PartectorBT on linux / mac

    # == Lifecycle and Context Management ==========================================================
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        """
        Initializes the scanner with the given event loop and queue.

        Args:
            loop (asyncio.AbstractEventLoop): The event loop to run the scanner in.
            queue (asyncio.Queue): The queue to store the scanned data.
        """
        self._loop = loop
        self._queue = queue
        self._setup()

    def _setup(self) -> None:
        """
        Initializes scanner internals (stop flag, task, and optional auto-start).
        """
        self._stop_event = asyncio.Event()
        self._stop_event.set()  # stopped by default
        self._task: asyncio.Task | None = None

    async def __aenter__(self) -> PartectorBleScanner:
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    def __del__(self) -> None:
        if not self._stop_event.is_set():
            self._loop.create_task(self.stop())

    # == Public Methods ============================================================================
    def start(self) -> None:
        """Starts the scanner."""
        if not self._stop_event.is_set():
            logger.warning("You called PartectorBleScaner.start() but scanner is already running.")
            return None

        logger.debug("Starting PartectorBleScanner...")
        self._stop_event.clear()
        self._task = self._loop.create_task(self.scan())

    async def stop(self) -> None:
        """Stops the scanner."""
        logger.debug("Stopping PartectorBleScanner...")
        self._stop_event.set()
        if (hasattr(self, "_task") and self._task) and not self._task.done():
            await self._task
        logger.debug("PartectorBleScanner stopped.")

    # == Internal Async Processing =================================================================
    async def _detection_callback(self, device: BLEDevice, adv: AdvertisementData) -> None:
        """Handles the callbacks from the BleakScanner used in the scan method.

        Args:
            device (BLEDevice): Bleak BLEDevice object
            adv (AdvertisementData): Bleak AdvertisementData object
        """

        if device.name not in self.BLE_NAMES_NANEOS:
            return None

        decoded_adv: bytes | None = PartectorBleDecoder.decode_partector_advertisement(adv)

        if decoded_adv:
            if self._queue.full():  # if the queue is full, make space by removing the oldest item
                await self._queue.get()

            await self._queue.put(decoded_adv)

    async def scan(self) -> None:
        """Scans for BLE devices and calls the _detection_callback method for each device found."""

        scanner = BleakScanner(self._detection_callback)

        while not self._stop_event.is_set():
            try:
                async with scanner:
                    await asyncio.sleep(0.8)
            except Exception as e:
                logger.exception(e)
                await asyncio.sleep(0.5)  # small backoff before retry


async def main():
    loop = asyncio.get_event_loop()
    queue_scanner = asyncio.Queue(maxsize=100)

    # classic way of using the scanner
    # scanner = PartectorBleScanner(loop=loop, queue=queue_scanner)
    # scanner.start()
    # try:
    #     await asyncio.sleep(2)  # Asynchronous sleep to allow the loop to run
    # finally:
    #     await scanner.stop()

    # using the context manager
    async with PartectorBleScanner(loop=loop, queue=queue_scanner):
        await asyncio.sleep(2)

    # Print the contents of the queue
    while not queue_scanner.empty():
        data = await queue_scanner.get()
        logger.info(f"Received data: {data}")


if __name__ == "__main__":
    asyncio.run(main())

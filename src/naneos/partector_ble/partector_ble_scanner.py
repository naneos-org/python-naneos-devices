import asyncio

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from naneos.logger import LEVEL_INFO, get_naneos_logger
from naneos.partector_ble.partector_ble_decoder import PartectorBleDecoder

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleScanner:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        auto_start: bool,
        queue: asyncio.Queue,
    ) -> None:
        self._loop = loop
        self._stop_event = asyncio.Event()
        self._stop_event.set()  # stopped by default
        self._queue = queue

        if auto_start:
            self.start()

    def start(self) -> None:
        """Starts the scanner."""
        if not self._stop_event.is_set():
            logger.warning("You called PartectorBleScaner.start()but scanner is already running.")
            return None

        self._stop_event.clear()
        self._task = self._loop.create_task(self.scan())

    async def stop(self) -> None:
        """Stops the scanner."""
        self._stop_event.set()
        if (hasattr(self, "_task") and self._task) and not self._task.done():
            await self._task
        logger.debug("PartectorBleScanner stopped.")

    async def _detection_callback(self, device: BLEDevice, adv: AdvertisementData) -> None:
        """Handles the callbacks from the BleakScanner used in the scan method.

        Args:
            device (BLEDevice): Bleak BLEDevice object
            data (AdvertisementData): Bleak AdvertisementData object
        """

        if device.name not in {"P2", "PartectorBT"}:  # P2 on windows, PartectorBT on linux / mac
            return None

        decoded_adv = PartectorBleDecoder.decode_std_chareristic(adv)

        if decoded_adv:
            if self._queue.full():  # if the queue is full, make space by removing the oldest item
                await self._queue.get()

            await self._queue.put(decoded_adv)

    async def scan(self) -> None:
        """Scans for BLE devices and calls the _detection_callback method for each device found."""

        scanner = BleakScanner(self._detection_callback)

        while not self._stop_event.is_set():
            async with scanner:
                await asyncio.sleep(0.8)


async def main():
    loop = asyncio.get_event_loop()
    queue_scanner = asyncio.Queue(maxsize=100)
    scanner = PartectorBleScanner(loop=loop, auto_start=True, queue=queue_scanner)
    try:
        await asyncio.sleep(2)  # Asynchronous sleep to allow the loop to run
    finally:
        await scanner.stop()

    while not queue_scanner.empty():
        data = await queue_scanner.get()
        logger.info(f"Received data: {data}")


if __name__ == "__main__":
    asyncio.run(main())

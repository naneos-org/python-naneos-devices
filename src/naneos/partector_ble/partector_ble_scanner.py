import asyncio

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from naneos.partector_ble.partector_ble_decoder import PartectorBleDecoder


class PartectorBleScanner:
    def __init__(self, loop: asyncio.AbstractEventLoop, auto_start: bool) -> None:
        self._loop = loop
        self._stop_event = asyncio.Event()
        self._stop_event.set()  # stopped by default

        if auto_start:
            self.start()

    def __del__(self) -> None:
        """Destructor for the scanner."""
        self.stop()

    def start(self) -> None:
        """Starts the scanner."""
        if not self._stop_event.is_set():
            print("Scanner already started")
            return None

        self._stop_event.clear()
        self._loop.create_task(self.scan())

    def stop(self) -> None:
        """Stops the scanner."""
        self._stop_event.set()

    async def _detection_callback(self, device: BLEDevice, adv: AdvertisementData) -> None:
        """Handles the callbacks from the BleakScanner used in the scan method.

        Args:
            device (BLEDevice): Bleak BLEDevice object
            data (AdvertisementData): Bleak AdvertisementData object
        """

        if device.name not in {"P2", "PartectorBT"}:  # P2 on windows, PartectorBT on linux / mac
            return None

        print(PartectorBleDecoder.decode_std_chareristic(adv))

    async def scan(self) -> None:
        """Scans for BLE devices and calls the _detection_callback method for each device found."""

        scanner = BleakScanner(self._detection_callback)

        while not self._stop_event.is_set():
            async with scanner:
                await asyncio.sleep(1.0)


async def main():
    loop = asyncio.get_event_loop()
    scanner = PartectorBleScanner(loop=loop, auto_start=True)
    try:
        await asyncio.sleep(5)  # Asynchronous sleep to allow the loop to run
    finally:
        scanner.stop()
        await asyncio.sleep(1)  # Allow cleanup tasks to complete


if __name__ == "__main__":
    asyncio.run(main())

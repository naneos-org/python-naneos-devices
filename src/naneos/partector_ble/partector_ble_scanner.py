import asyncio

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from naneos.partector_ble.partector_ble_decoder import PartectorBleDecoder


class PartectorBleScanner:
    async def _detection_callback(self, device: BLEDevice, data: AdvertisementData) -> None:
        """Handles all the callbacks from the BleakScanner used in the scan method.

        Args:
            device (BLEDevice): Bleak BLEDevice object
            data (AdvertisementData): Bleak AdvertisementData object
        """
        if device.name not in ["P2", "PartectorBT"]:
            return None

        print(PartectorBleDecoder.decode_std_chareristic(data))

    async def scan(self) -> None:
        """Scans for BLE devices and calls the _detection_callback method for each device found."""
        async with BleakScanner(self._detection_callback) as scanner:
            await scanner.start()
            await asyncio.sleep(2.0)
            await scanner.stop()


if __name__ == "__main__":
    scanner = PartectorBleScanner()
    asyncio.run(scanner.scan())

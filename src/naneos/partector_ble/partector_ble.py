import asyncio
from threading import Event, Thread
import time

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from naneos.logger import LEVEL_DEBUG, get_naneos_logger
from naneos.partector_ble.partector_ble_device import PartectorBleDevice

logger = get_naneos_logger(__name__, LEVEL_DEBUG)


class PartectorBle(Thread):
    SERVICE_UUID = "0bd51666-e7cb-469b-8e4d-2742f1ba77cc"
    CHAR_STD = "e7add780-b042-4876-aae1-112855353cc1"
    CHAR_AUX = "e7add781-b042-4876-aae1-112855353cc1"
    CHAR_WRITE = "e7add782-b042-4876-aae1-112855353cc1"
    CHAR_READ = "e7add783-b042-4876-aae1-112855353cc1"
    CHAR_SIZE_DIST = "e7add784-b042-4876-aae1-112855353cc1"

    def __init__(self) -> None:
        super().__init__()
        self.event = Event()

        self._devices_to_connect: dict[BLEDevice, int] = {}
        self._connected_clients: dict[BleakClient, PartectorBleDevice] = {}

    def run(self) -> None:
        """Main loop of the partector BLE thread"""
        asyncio.run(self.async_run())

    async def async_run(self) -> None:
        """Async implementation of the main loop of the partector BLE thread

        This is needed to use BleakScanner and BleakClient in the same thread
        """
        while not self.event.is_set():
            await self.scan()
            await self.connect()

        await self._disconnect()

    async def scan(self) -> None:
        """Scans for old and new Partector BLE protocol devices

        The magic happens in the _detection_callback method.
        New Partectors are added to the _devices_to_connect dict and connected to in the connect method.
        TODO Old Partectors search for their corresponding object and add their data with timestamp.
        """
        async with BleakScanner(detection_callback=self._detection_callback) as scanner:
            await scanner.start()
            await asyncio.sleep(0.85)
            await scanner.stop()

    async def connect(self) -> None:
        """Connects to all devices in the _devices_to_connect dict.

        TODO: All the possible characteristics are detected and added to a notification service.
        """
        for device, serial_number in self._devices_to_connect.items():
            logger.debug(f"Trying to connect to {device.name} with serial number {serial_number}")

            client = BleakClient(device, self._disconnected_callback, timeout=1)
            await client.connect()

            callbacks = PartectorBleDevice(serial_number)
            await client.start_notify(self.CHAR_STD, callbacks.callback_std)

            self._connected_clients[client] = callbacks

            logger.info(f"Connected to {device.name} with serial number {serial_number}")

        self._devices_to_connect.clear()

    async def _disconnect(self) -> None:
        """Disconnect from all connected devices.

        This is done with range in for loop because client disconnect removes the client from the dict.
        A while loop would not be safe because if something goes wrong the thread would never close.
        """
        for _ in range(len(self._connected_clients)):
            client = next(iter(self._connected_clients.keys()))
            logger.debug(f"Disconnecting from {self._connected_clients[client].serial_number}")
            await client.disconnect()

        logger.info("Disconnected from all BLE devices")

    async def _detection_callback(self, device: BLEDevice, data: AdvertisementData) -> None:
        """Handles all the callbacks from the BleakScanner used in the scan method.

        Args:
            device (BLEDevice): Bleak BLEDevice object
            data (AdvertisementData): Bleak AdvertisementData object
        """
        if device.name == "P2":
            await self._detection_callback_old(device, data)
        elif device.name == "PartectorBT":
            await self._detection_callback_new(device, data)

    # TODO: Implement old Partector BLE protocol
    async def _detection_callback_old(self, device: BLEDevice, data: AdvertisementData) -> None:
        pass

    async def _detection_callback_new(self, device: BLEDevice, data: AdvertisementData) -> None:
        """Handles the callbacks for devices with the name PartectorBT (new Partector BLE protocol)

        Args:
            device (BLEDevice): Bleak BLEDevice object
            data (AdvertisementData): Bleak AdvertisementData object
        """
        _, sn = PartectorBleDevice.get_naneos_adv(data)

        if not sn or sn in [client.serial_number for client in self._connected_clients.values()]:
            return None

        self._devices_to_connect[device] = sn

    def _disconnected_callback(self, client: BleakClient) -> None:
        """Removes the client from the _connected_clients dict when it disconnects.

        Args:
            client (BleakClient): BleakClient object
        """
        logger.debug(f"Disconnected from {self._connected_clients[client].serial_number}")
        self._connected_clients.pop(client)


if __name__ == "__main__":
    partector_ble = PartectorBle()
    partector_ble.start()
    time.sleep(4)
    partector_ble.event.set()
    partector_ble.join()

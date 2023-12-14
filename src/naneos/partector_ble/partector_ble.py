import asyncio
from collections import deque
from threading import Event, Thread
import time
from typing import Optional

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

    def __init__(self, serial_numbers: Optional[list[int]] = None) -> None:
        super().__init__()
        self.event = Event()

        self._serial_numbers = serial_numbers

        """Dict of all devices that are found in the scan method."""
        self._devices_to_check: dict[BLEDevice, tuple[int, AdvertisementData]] = {}
        """Dict containing all connected devices, that are in use."""
        self._partector_clients: dict[int, PartectorBleDevice] = {}

        self._send_queue: deque[tuple[int, str]] = deque(maxlen=10)

    def run(self) -> None:
        """Main loop of the partector BLE thread"""
        # asyncio.run(self.async_run())

        # run async_run and async_send_command in the same thread
        async def test() -> None:
            await asyncio.gather(self._async_run(), self._async_send_command())

        asyncio.run(test())

    async def _async_run(self) -> None:
        """Async implementation of the main loop of the partector BLE thread

        This is needed to use BleakScanner and BleakClient in the same thread
        """
        timestamp = int(time.time())  # unix timestamp in seconds
        while not self.event.is_set():
            if time.time() >= timestamp + 1:
                timestamp = int(time.time())

            await self.scan()
            await self.check_scans()

        await self._disconnect()

    async def _async_send_command(self) -> None:
        """Runs parallel to the scan an get functions and sends if somethin is pushed into the send queue"""
        while not self.event.is_set():
            if self._send_queue:
                serial_number, command = self._send_queue.popleft()
                if serial_number not in self._partector_clients:
                    logger.warning(f"Serial number {serial_number} not found")
                    continue

                client = self._partector_clients[serial_number].ble_client
                if client is None:
                    logger.warning(f"Serial number {serial_number} not connected")
                    continue
                else:
                    await client.write_gatt_char(self.CHAR_WRITE, command.encode())
                    logger.info(f"Sent {command} to {serial_number}")

            await asyncio.sleep(0.1)

    def send_command(self, serial_number: int, command: str) -> None:
        self._send_queue.append((serial_number, command))

    async def scan(self) -> None:
        """Scans for old and new Partector BLE protocol devices

        All found devices are added to the _devices_to_check dict in the _detection_callback method.
        Scan duration of 850ms is used because the advertised data of the old devices changes every 1s.
        """
        async with BleakScanner(detection_callback=self._detection_callback) as scanner:
            await scanner.start()
            await asyncio.sleep(0.85)
            await scanner.stop()

    async def check_scans(self) -> None:
        """Tries to connect to all devices in the _devices_to_connect dict.

        If the device is a old one, the advertisement data will be parsed and added to an partector_ble_device object.
        """
        for device, values in self._devices_to_check.items():
            if values[0] not in self._partector_clients:
                self._partector_clients[values[0]] = PartectorBleDevice(values[0])

            client = BleakClient(device, self._disconnected_callback, timeout=1)

            try:
                await client.connect()
            except asyncio.TimeoutError:
                self._add_old_device_data(values)
                continue

            my_ble_device = self._partector_clients[values[0]]
            if my_ble_device.ble_client:
                return None

            await client.start_notify(self.CHAR_STD, my_ble_device.callback_std)
            await client.start_notify(self.CHAR_AUX, my_ble_device.callback_aux)
            await client.start_notify(self.CHAR_READ, my_ble_device.callback_read)
            await client.start_notify(self.CHAR_SIZE_DIST, my_ble_device.callback_size_dist)

            my_ble_device.ble_client = client

            logger.info(
                f"Connected to {device.name} {device.address} with serial number {values[0]}"
            )

        self._devices_to_check.clear()

    def _add_old_device_data(self, values: tuple[int, AdvertisementData]) -> None:
        serial_number = values[0]
        adv = values[1]

        self._partector_clients[serial_number]._add_old_format_data(adv, serial_number)

    async def _disconnect(self) -> None:
        """Disconnect from all connected devices.

        This is done with range in for loop because client disconnect removes the client from the dict.
        A while loop would not be safe because if something goes wrong the thread would never close.
        """
        devices = list(self._partector_clients)
        for device in devices:
            logger.debug(f"Disconnecting from {device}")
            if self._partector_clients[device].ble_client is not None:
                await self._partector_clients[device].ble_client.disconnect()  # type: ignore

        logger.info("Disconnected from all BLE devices")

    async def _detection_callback(self, device: BLEDevice, data: AdvertisementData) -> None:
        """Handles all the callbacks from the BleakScanner used in the scan method.

        Args:
            device (BLEDevice): Bleak BLEDevice object
            data (AdvertisementData): Bleak AdvertisementData object
        """
        if device.name not in ["P2", "PartectorBT"]:
            return None

        _, sn = PartectorBleDevice.get_naneos_adv(data)

        if sn is None:  # return None if no serial number is found
            return None

        # return None if serial number is not in the list of serial numbers
        if self._serial_numbers is not None and sn not in self._serial_numbers:
            return None

        connected = [x.serial_number for x in self._partector_clients.values()]
        if sn in connected:
            return None

        logger.info(f"Found {device.name} {device.address} with serial number {sn}")
        self._devices_to_check[device] = (sn, data)

    def _disconnected_callback(self, client: BleakClient) -> None:
        """Removes the client from the _connected_clients dict when it disconnects.

        Args:
            client (BleakClient): BleakClient object
        """
        serial_number = next(
            x.serial_number for x in self._partector_clients.values() if x.ble_client == client
        )
        logger.debug(f"Disconnected from {serial_number}")
        self._partector_clients.pop(serial_number)


if __name__ == "__main__":
    partector_ble = PartectorBle(serial_numbers=[8112, 8446])
    partector_ble.start()
    time.sleep(5)
    partector_ble.send_command(8112, "N?")
    time.sleep(15)
    # print(partector_ble._partector_clients[8112]._data_queue)
    partector_ble.event.set()
    partector_ble.join()

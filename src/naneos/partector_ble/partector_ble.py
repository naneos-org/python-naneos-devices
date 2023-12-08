import asyncio
from threading import Event, Thread
import time

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from naneos.partector_ble.partector_ble_callbacks import PartectorBleCallbacks


class PartectorBle(Thread):
    SERVICE_UUID: str = "0bd51666-e7cb-469b-8e4d-2742f1ba77cc"
    CHAR_STD: str = "e7add780-b042-4876-aae1-112855353cc1"
    CHAR_AUX: str = "e7add781-b042-4876-aae1-112855353cc1"
    CHAR_WRITE: str = "e7add782-b042-4876-aae1-112855353cc1"
    CHAR_READ: str = "e7add783-b042-4876-aae1-112855353cc1"
    CHAR_SIZE_DIST: str = "e7add784-b042-4876-aae1-112855353cc1"

    def __init__(self) -> None:
        super().__init__()
        self.event = Event()

        self._devices_to_connect: dict[BLEDevice, int] = {}
        self._connected_clients: dict[BleakClient, PartectorBleCallbacks] = {}

    def run(self) -> None:
        asyncio.run(self.async_run())

    async def async_run(self) -> None:
        while not self.event.is_set():
            await self.scan()
            await self.connect()

        await self.disconnect()

    async def disconnect(self) -> None:
        while self._connected_clients:
            client: BleakClient = next(iter(self._connected_clients.keys()))
            serial_number: int = self._connected_clients[client].serial_number
            print(f"Disconnecting from {serial_number}")
            await client.disconnect()

    # detection callback using AdvertisementDataCallback Type alias
    async def _detection_callback(self, device: BLEDevice, data: AdvertisementData) -> None:
        # PartectorBT is connectable
        # P2 is not connectable old Protocol
        if device.name not in ["PartectorBT"]:
            return

        man_data: bytes = next(iter(data.manufacturer_data.keys())).to_bytes(2, byteorder="little")
        start_symbol: str = man_data[0].to_bytes(1).decode("utf-8")
        if start_symbol != "X":
            return

        man_data += next(iter(data.manufacturer_data.values()))
        if len(man_data) != 22:
            return

        serial_number: int = int.from_bytes(man_data[15:17], byteorder="little")
        if serial_number in [sn.serial_number for sn in self._connected_clients.values()]:
            return

        self._devices_to_connect[device] = serial_number

    async def scan(self) -> None:
        # scan for devices with name "P2" and call _detection_callback
        async with BleakScanner(detection_callback=self._detection_callback) as scanner:
            await scanner.start()
            await asyncio.sleep(2)
            await scanner.stop()

    def _disconnected_callback(self, client: BleakClient) -> None:
        print(f"Disconnected from {client.address}")
        self._connected_clients.pop(client)

    def _notification_test_callback(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        print(sender)
        print(f"Received data: {data}")

    async def connect(self) -> None:
        while self._devices_to_connect:
            device: BLEDevice = next(iter(self._devices_to_connect.keys()))
            serial_number: int = self._devices_to_connect[device]
            self._devices_to_connect.pop(device)

            print(f"Checking device: {device.name} with serial number {serial_number}")

            client = BleakClient(
                device,
                timeout=2,
                disconnected_callback=self._disconnected_callback,
            )
            await client.connect()

            callbacks = PartectorBleCallbacks(serial_number)

            await client.start_notify(
                "e7add780-b042-4876-aae1-112855353cc1", callbacks.callback_std
            )

            self._connected_clients[client] = callbacks

            print(f"Connected to {device.name} with serial number {serial_number}")


if __name__ == "__main__":
    partector_ble = PartectorBle()
    partector_ble.start()
    time.sleep(10)
    partector_ble.event.set()
    partector_ble.join()

from __future__ import annotations

import asyncio

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakDeviceNotFoundError

from naneos.logger import LEVEL_INFO, get_naneos_logger

logger = get_naneos_logger(__name__, LEVEL_INFO)


class PartectorBleConnection:
    SERVICE_UUID = "0bd51666-e7cb-469b-8e4d-2742f1ba77cc"
    CHAR_STD = "e7add780-b042-4876-aae1-112855353cc1"
    CHAR_AUX = "e7add781-b042-4876-aae1-112855353cc1"
    CHAR_WRITE = "e7add782-b042-4876-aae1-112855353cc1"
    CHAR_READ = "e7add783-b042-4876-aae1-112855353cc1"
    CHAR_SIZE_DIST = "e7add784-b042-4876-aae1-112855353cc1"

    # == Lifecycle and Context Management ==========================================================
    def __init__(self, device: BLEDevice, loop: asyncio.AbstractEventLoop, serial: int) -> None:
        """
        Initializes the BLE connection with the given device, event loop, and queue.

        Args:
            device (BLEDevice): The BLE device to connect to.
            loop (asyncio.AbstractEventLoop): The event loop to run the connection in.
        """
        self._serial_number = serial

        self._loop = loop
        self._stop_event = asyncio.Event()
        self._stop_event.set()  # stopped by default
        self._task: asyncio.Task | None = None

        self._device = device
        # 5 seconds timeout is needed on windows for the connection to be established
        self._client = BleakClient(device, self._disconnect_callback, timeout=5)

    async def __aenter__(self) -> PartectorBleConnection:
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    # == Public Methods ============================================================================
    def start(self) -> None:
        """Starts the scanner."""
        if not self._stop_event.is_set():
            logger.warning("You called PartectorBleConnection.start() but is already running.")
            return

        logger.debug("Starting PartectorBleConnection...")
        self._stop_event.clear()
        self._task = self._loop.create_task(self.handle_connection())

    async def stop(self) -> None:
        """Stops the scanner."""
        logger.info("Stopping PartectorBleConnection...")
        self._stop_event.set()
        if self._task and not self._task.done():
            await self._task
        logger.info("PartectorBleConnection stopped.")

    async def handle_connection(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(0.5)
                if self._client.is_connected:
                    continue

                await self._client.connect()
                logger.info(f"Connected to {self._device.name} ({self._device.address})")
                await self._client.start_notify(self.CHAR_STD, self._callback_std)
                logger.info(f"Started notification on {self.CHAR_STD}")
            except asyncio.TimeoutError:
                logger.warning(f"Probably an old device {self._serial_number}, retrying soon.")
                # self._add_old_device_data(values)
                # TODO: mark as connected or old device
                continue
            except BleakDeviceNotFoundError:
                # TODO: mark as connected or old device
                continue
            except Exception as e:
                logger.exception(f"Exception for {self._serial_number} connection: {e}")

        if self._client.is_connected:
            await self._client.stop_notify(self.CHAR_STD)
            logger.info(f"Stopped notification on {self.CHAR_STD}")
            await self._client.disconnect()

    def _disconnect_callback(self, client: BleakClient) -> None:
        """
        Callback function to be called when the client is disconnected.
        """
        logger.info(f"Disconnected from {self._device.name} ({self._device.address})")

    def _callback_std(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """
        Callback function to be called when data is received from the standard characteristic.
        """
        logger.info(f"Received data from {self._device.name}: {data.hex()}")


async def main():
    from naneos.partector_ble.decoder.partector_ble_decoder_std import PartectorBleDecoderStd
    from naneos.partector_ble.partector_ble_scanner import PartectorBleScanner

    loop = asyncio.get_event_loop()
    queue_scanner = asyncio.Queue(maxsize=100)

    async with PartectorBleScanner(loop=loop, queue=queue_scanner):
        await asyncio.sleep(2)

    device = None
    while not queue_scanner.empty():
        data = queue_scanner.get_nowait()
        serial_number = PartectorBleDecoderStd.decode(data[1][0], data_structure=None).serial_number
        logger.info(f"Got serial number {serial_number}")
        if serial_number == 8112:
            device = data[0]
            break

    if device is None:
        logger.info("No device found with serial number 8112.")
        return

    async with PartectorBleConnection(device=device, loop=loop, serial=8112):
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())

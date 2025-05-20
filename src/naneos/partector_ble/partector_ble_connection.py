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
            logger.warning("SN{self._serial_number}: start() called while already running")
            return

        self._stop_event.clear()
        self._task = self._loop.create_task(self.handle_connection())

    async def stop(self) -> None:
        """Stops the scanner."""
        self._stop_event.set()
        if self._task and not self._task.done():
            await self._task
        logger.info(f"SN{self._serial_number}: PartectorBleConnection stopped")

    async def handle_connection(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(0.5)
                if self._client.is_connected:
                    continue

                await self._client.connect()
                await self._client.start_notify(self.CHAR_STD, self._callback_std)
                logger.info(f"SN{self._serial_number}: Connected to {self._device.address}")
            except asyncio.TimeoutError:
                logger.warning(f"SN{self._serial_number}: Connection timeout.")
                await asyncio.sleep(4.5)
                # self._add_old_device_data(values)
                # TODO: mark as connected or old device
            except BleakDeviceNotFoundError:
                logger.warning(f"SN{self._serial_number}: Device not found.")
                await asyncio.sleep(4.5)
                # TODO: mark as connected or old device
            except Exception as e:
                logger.exception(f"SN{self._serial_number}: Unknown exception: {e}")
                await asyncio.sleep(4.5)

        if self._client.is_connected:
            try:
                await asyncio.wait_for(self._client.stop_notify(self.CHAR_STD), timeout=5)
            except Exception as e:
                logger.exception(f"SN{self._serial_number}: stop_notify CHAR_STD: {e}")
            try:
                await asyncio.wait_for(self._client.disconnect(), timeout=5)
            except Exception as e:
                logger.exception(f"SN{self._serial_number}: Disconnect failed: {e}")

    def _disconnect_callback(self, client: BleakClient) -> None:
        """
        Callback function to be called when the client is disconnected.
        """
        logger.debug(f"SN{self._serial_number}: Disconnect callback called")

    def _callback_std(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """
        Callback function to be called when data is received from the standard characteristic.
        """
        logger.info(f"SN{self._serial_number}: Received data: {data.hex()}")


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

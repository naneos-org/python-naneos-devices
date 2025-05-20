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
    CHAR_UUIDS = {
        "std": "e7add780-b042-4876-aae1-112855353cc1",
        "aux": "e7add781-b042-4876-aae1-112855353cc1",
        "write": "e7add782-b042-4876-aae1-112855353cc1",
        "read": "e7add783-b042-4876-aae1-112855353cc1",
        "size_dist": "e7add784-b042-4876-aae1-112855353cc1",
    }

    # == Lifecycle and Context Management ==========================================================
    def __init__(
        self, device: BLEDevice, loop: asyncio.AbstractEventLoop, serial_number: int
    ) -> None:
        """
        Initializes the BLE connection with the given device, event loop, and queue.

        Args:
            device (BLEDevice): The BLE device to connect to.
            loop (asyncio.AbstractEventLoop): The event loop to run the connection in.
            serial_number (int): The serial number of the device.
        """
        self._serial_number = serial_number
        self._device = device
        self._loop = loop
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._stop_event.set()  # stopped by default
        # 5 seconds timeout is needed on windows for the connection to be established
        self._client = BleakClient(device, self._disconnect_callback, timeout=30)

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
        self._task = self._loop.create_task(self._run())

    async def stop(self) -> None:
        """Stops the scanner."""
        self._stop_event.set()
        if self._task and not self._task.done():
            await self._task
        logger.info(f"SN{self._serial_number}: PartectorBleConnection stopped")

    async def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    await asyncio.sleep(0.5)
                    if self._client.is_connected:
                        continue

                    await self._client.connect()
                    await self._client.start_notify(self.CHAR_UUIDS["std"], self._callback_std)
                    await self._client.start_notify(self.CHAR_UUIDS["aux"], self._callback_aux)
                    await self._client.start_notify(self.CHAR_UUIDS["size_dist"], self._callback_size_dist)
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
                    logger.warning(f"SN{self._serial_number}: Unknown exception: {e}")
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.warning(f"SN{self._serial_number}: _run task cancelled.")
        except Exception as e:
            logger.exception(f"SN{self._serial_number}: _run task failed: {e}")
        finally:
            await self._disconnect_gracefully()

    async def _disconnect_gracefully(self) -> None:
        if not self._client.is_connected:
            return

        try:
            await asyncio.wait_for(self._client.stop_notify(self.CHAR_UUIDS["std"]), timeout=30)
            await asyncio.sleep(0.5)  # wait for windows to free resources
            await asyncio.wait_for(self._client.stop_notify(self.CHAR_UUIDS["aux"]), timeout=30)
            await asyncio.sleep(0.5)  # wait for windows to free resources
            await asyncio.wait_for(self._client.stop_notify(self.CHAR_UUIDS["size_dist"]), timeout=30)
            await asyncio.sleep(0.5)  # wait for windows to free resources
        except Exception as e:
            logger.exception(f"SN{self._serial_number}: Failed to stop notify: {e}")

        try:
            await asyncio.wait_for(self._client.disconnect(), timeout=30)
            await asyncio.sleep(1)  # wait for windows to free resources
        except Exception as e:
            logger.exception(f"SN{self._serial_number}: Failed to disconnect: {e}")

    def _disconnect_callback(self, client: BleakClient) -> None:
        """Callback on disconnect."""
        logger.debug(f"SN{self._serial_number}: Disconnect callback called")

    def _callback_std(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Callback on data received (std characteristic)."""
        logger.info(f"SN{self._serial_number}: Received std: {data.hex()}")
    
    def _callback_aux(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Callback on data received (aux characteristic)."""
        logger.info(f"SN{self._serial_number}: Received aux: {data.hex()}")

    def _callback_size_dist(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Callback on data received (size_dist characteristic)."""
        logger.info(f"SN{self._serial_number}: Received size: {data.hex()}")


async def main():
    from naneos.partector_ble.partector_ble_scanner import PartectorBleScanner

    SN = 8112

    loop = asyncio.get_event_loop()
    queue = asyncio.Queue(maxsize=100)

    async with PartectorBleScanner(loop=loop, queue=queue):
        await asyncio.sleep(4)

    device = await _find_device_with_serial(queue, target_serial=SN)
    if not device:
        logger.info(f"No device found with serial number {SN}.")
        return

    async with PartectorBleConnection(device=device, loop=loop, serial_number=SN):
        await asyncio.sleep(10)


async def _find_device_with_serial(queue: asyncio.Queue, target_serial: int) -> BLEDevice | None:
    from naneos.partector_ble.decoder.partector_ble_decoder_std import PartectorBleDecoderStd

    while not queue.empty():
        device, data = await queue.get()
        serial = PartectorBleDecoderStd.decode(data[0], data_structure=None).serial_number
        logger.info(f"Found device with serial {serial}")
        if serial == target_serial:
            return device
    return None


async def main_x(x):
    for _ in range(x):
        await main()


if __name__ == "__main__":
    asyncio.run(main_x(20))

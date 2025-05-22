from __future__ import annotations

import asyncio
import time
from typing import Optional

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakDeviceNotFoundError

from naneos.logger import LEVEL_INFO, get_naneos_logger
from naneos.partector.blueprints._data_structure import Partector2DataStructure
from naneos.partector_ble.decoder.partector_ble_decoder_aux import PartectorBleDecoderAux
from naneos.partector_ble.decoder.partector_ble_decoder_size import PartectorBleDecoderSize
from naneos.partector_ble.decoder.partector_ble_decoder_std import PartectorBleDecoderStd

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

    # static methods ###############################################################################
    @staticmethod
    def create_connection_queue() -> asyncio.Queue[Partector2DataStructure]:
        """Create a queue for the scanner."""
        queue_connection: asyncio.Queue[Partector2DataStructure] = asyncio.Queue(maxsize=100)

        return queue_connection

    # == Lifecycle and Context Management ==========================================================
    def __init__(
        self,
        device: BLEDevice,
        loop: asyncio.AbstractEventLoop,
        serial_number: int,
        queue: asyncio.Queue[Partector2DataStructure],
    ) -> None:
        """
        Initializes the BLE connection with the given device, event loop, and queue.

        Args:
            device (BLEDevice): The BLE device to connect to.
            loop (asyncio.AbstractEventLoop): The event loop to run the connection in.
            serial_number (int): The serial number of the device.
        """
        self.SERIAL_NUMBER = serial_number
        self._data = Partector2DataStructure()
        self._next_ts = 0.0
        self._queue = queue

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
        logger.info(f"SN{self.SERIAL_NUMBER}: PartectorBleConnection stopped")

    async def _run(self) -> None:
        try:
            self._next_ts = int(time.time()) + 1.0

            while not self._stop_event.is_set():
                try:
                    wait = self._next_ts - time.time()
                    if wait > 0:
                        await asyncio.sleep(wait)
                        self._next_ts += 1.0
                    else:
                        logger.warning(f"SN{self.SERIAL_NUMBER}: Waiting time negative: {wait}")
                        self._next_ts = int(time.time()) + 1.0

                    if self._client.is_connected:
                        self._queue.put_nowait(self._data)
                        self._data = Partector2DataStructure()
                        continue

                    await self._client.connect()
                    await self._client.start_notify(self.CHAR_UUIDS["std"], self._callback_std)
                    await self._client.start_notify(self.CHAR_UUIDS["aux"], self._callback_aux)
                    await self._client.start_notify(
                        self.CHAR_UUIDS["size_dist"], self._callback_size_dist
                    )
                    logger.info(f"SN{self.SERIAL_NUMBER}: Connected to {self._device.address}")
                    self._next_ts = int(time.time()) + 1.0
                except asyncio.TimeoutError:
                    logger.warning(f"SN{self.SERIAL_NUMBER}: Connection timeout.")
                    await asyncio.sleep(4.5)
                    # self._add_old_device_data(values)
                    # TODO: mark as connected or old device
                except BleakDeviceNotFoundError:
                    logger.warning(f"SN{self.SERIAL_NUMBER}: Device not found.")
                    await asyncio.sleep(4.5)
                    # TODO: mark as connected or old device
                except Exception as e:
                    logger.warning(f"SN{self.SERIAL_NUMBER}: Unknown exception: {e}")
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.warning(f"SN{self.SERIAL_NUMBER}: _run task cancelled.")
        except Exception as e:
            logger.exception(f"SN{self.SERIAL_NUMBER}: _run task failed: {e}")
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
            await asyncio.wait_for(
                self._client.stop_notify(self.CHAR_UUIDS["size_dist"]), timeout=30
            )
            await asyncio.sleep(0.5)  # wait for windows to free resources
        except Exception as e:
            logger.exception(f"SN{self.SERIAL_NUMBER}: Failed to stop notify: {e}")

        try:
            await asyncio.wait_for(self._client.disconnect(), timeout=30)
            await asyncio.sleep(1)  # wait for windows to free resources
        except Exception as e:
            logger.exception(f"SN{self.SERIAL_NUMBER}: Failed to disconnect: {e}")

    def _disconnect_callback(self, client: BleakClient) -> None:
        """Callback on disconnect."""
        logger.debug(f"SN{self.SERIAL_NUMBER}: Disconnect callback called")

    def _callback_std(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Callback on data received (std characteristic)."""
        self._data.unix_timestamp = int(time.time() * 1000)
        PartectorBleDecoderStd.decode(data, data_structure=self._data)

        logger.debug(f"SN{self.SERIAL_NUMBER}: Received std: {data.hex()}")

    def _callback_aux(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Callback on data received (aux characteristic)."""
        self._data.unix_timestamp = int(time.time() * 1000)
        PartectorBleDecoderAux.decode(data, data_structure=self._data)

        logger.debug(f"SN{self.SERIAL_NUMBER}: Received aux: {data.hex()}")

    def _callback_size_dist(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Callback on data received (size_dist characteristic)."""
        self._data.unix_timestamp = int(time.time() * 1000)
        PartectorBleDecoderSize.decode(data, data_structure=self._data)

        logger.debug(f"SN{self.SERIAL_NUMBER}: Received size: {data.hex()}")


async def main():
    from naneos.partector_ble.partector_ble_scanner import PartectorBleScanner

    SNS = {8112, 8617}
    conn_list = []  # serial number to connection mapping

    loop = asyncio.get_event_loop()
    queue_scanner = PartectorBleScanner.create_scanner_queue()
    queue_connection = PartectorBleConnection.create_connection_queue()

    async with PartectorBleScanner(loop=loop, queue=queue_scanner):
        await asyncio.sleep(5)

    device_dict = await _map_sn_to_device(queue_scanner)
    if not device_dict:
        return

    device_dict = {k: v for k, v in device_dict.items() if k in SNS}

    # start connections for all devices
    for serial_number, device in device_dict.items():
        conn_list.append(
            PartectorBleConnection(
                device=device, loop=loop, serial_number=serial_number, queue=queue_connection
            )
        )
        conn_list[-1].start()

    await asyncio.sleep(10)

    # stop connections for all devices
    for conn in conn_list:
        await conn.stop()

    # print the data from the queue
    while not queue_connection.empty():
        data = await queue_connection.get()
        print(data)


async def _map_sn_to_device(
    queue: asyncio.Queue[tuple[BLEDevice, tuple[bytes, Optional[bytes]]]],
) -> Optional[dict[int, BLEDevice]]:
    device_dict = {}
    while not queue.empty():
        device, data = await queue.get()
        serial = PartectorBleDecoderStd.decode(data[0], data_structure=None).serial_number
        if serial:
            device_dict[serial] = device

    if not device_dict:
        logger.info("No devices found.")
        return None

    return device_dict


async def main_x(x):
    for _ in range(x):
        await main()


if __name__ == "__main__":
    asyncio.run(main_x(3))

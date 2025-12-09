from __future__ import annotations

import asyncio
import time
from typing import Optional

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakDeviceNotFoundError

from naneos.logger import LEVEL_WARNING, get_naneos_logger
from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint
from naneos.partector_ble.decoder.partectod_ble_decoder_aux_error import PartectorBleDecoderAuxError
from naneos.partector_ble.decoder.partector_ble_decoder_aux import PartectorBleDecoderAux
from naneos.partector_ble.decoder.partector_ble_decoder_size import PartectorBleDecoderSize
from naneos.partector_ble.decoder.partector_ble_decoder_std import PartectorBleDecoderStd

logger = get_naneos_logger(__name__, LEVEL_WARNING)


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
    def create_connection_queue() -> asyncio.Queue[NaneosDeviceDataPoint]:
        """Create a queue for the connection data."""
        # Increased maxsize to 500 to handle bursts from multiple devices
        # Prevents message loss on Raspberry Pi with many concurrent connections
        queue_connection: asyncio.Queue[NaneosDeviceDataPoint] = asyncio.Queue(maxsize=500)

        return queue_connection

    # == Lifecycle and Context Management ==========================================================
    def __init__(
        self,
        device: BLEDevice,
        loop: asyncio.AbstractEventLoop,
        serial_number: int,
        queue: asyncio.Queue[NaneosDeviceDataPoint],
    ) -> None:
        """
        Initializes the BLE connection with the given device, event loop, and queue.

        Args:
            device (BLEDevice): The BLE device to connect to.
            loop (asyncio.AbstractEventLoop): The event loop to run the connection in.
            serial_number (int): The serial number of the device.
        """
        self.SERIAL_NUMBER = serial_number
        self._device_type = NaneosDeviceDataPoint.DEV_TYPE_P2  # Thats the deafault value
        self._data = NaneosDeviceDataPoint()
        self._next_ts = 0.0
        self._last_aux_data_ts = time.time()
        self._queue = queue

        # Decode queue to decouple decoding from BLE callbacks
        # This prevents blocking the event loop when decoding heavy data
        self._decode_queue: asyncio.Queue = asyncio.Queue(maxsize=200)

        self._device = device
        self._loop = loop
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._stop_event.set()  # stopped by default
        self._client = BleakClient(device, self._disconnect_callback, timeout=10)

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
        waiting_seconds = 0

        try:
            self._next_ts = int(time.time()) + 1.0

            # Create decode task to run in parallel
            # This prevents decoding from blocking the event loop
            self._loop.create_task(self._decode_routine())

            while not self._stop_event.is_set():
                try:
                    if self._last_aux_data_ts + 60 < time.time():
                        logger.info(
                            f"SN{self.SERIAL_NUMBER}: No aux data received for 60 seconds, disconnecting to reset."
                        )
                        await self._disconnect_gracefully()
                        self._last_aux_data_ts = time.time()
                        waiting_seconds = 5  # wait 5 seconds before reconnecting

                    waiting_seconds = max(0, waiting_seconds - 1)
                    wait = self._next_ts - time.time()
                    if wait > 0:
                        await asyncio.sleep(wait)
                        self._next_ts += 1.0
                    else:
                        if self._client.is_connected:
                            logger.info(f"SN{self.SERIAL_NUMBER}: Waiting time negative: {wait}")
                        self._next_ts = int(time.time()) + 1.0

                    if self._client.is_connected:
                        if (
                            self._device_type == NaneosDeviceDataPoint.DEV_TYPE_P2PRO
                            and self._data.particle_number_10nm is None
                            and self._data.particle_number_16nm is None
                            and self._data.particle_number_26nm is None
                            and self._data.particle_number_43nm is None
                            and self._data.particle_number_70nm is None
                            and self._data.particle_number_114nm is None
                            and self._data.particle_number_185nm is None
                            and self._data.particle_number_300nm is None
                        ):
                            self._data.particle_number_concentration = None
                            self._data.average_particle_diameter = None

                        self._queue.put_nowait(self._data)
                        self._data = NaneosDeviceDataPoint(
                            device_type=self._device_type,
                            serial_number=self.SERIAL_NUMBER,
                            connection_type=NaneosDeviceDataPoint.CONN_TYPE_CONNECTED,
                            # TODO: add firware version from device here
                        )
                        continue

                    if waiting_seconds == 0:
                        await self._client.connect(timeout=5)  # 5 seconds for windows...
                        if self._client.is_connected:
                            await self._client.start_notify(
                                self.CHAR_UUIDS["std"], self._callback_std
                            )
                            await self._client.start_notify(
                                self.CHAR_UUIDS["aux"], self._callback_aux
                            )
                            await self._client.start_notify(
                                self.CHAR_UUIDS["size_dist"], self._callback_size_dist
                            )
                        logger.info(f"SN{self.SERIAL_NUMBER}: Connected to {self._device.address}")

                    self._next_ts = int(time.time()) + 1.0
                except asyncio.TimeoutError:
                    logger.info(f"SN{self.SERIAL_NUMBER}: Connection timeout.")
                    waiting_seconds = 30
                    await asyncio.sleep(0.5)
                except BleakDeviceNotFoundError:
                    logger.info(f"SN{self.SERIAL_NUMBER}: Device not found or probably old BLE.")
                    waiting_seconds = 30
                    await asyncio.sleep(0.5)
                except Exception as e:
                    # if exception contains "not found" increase waiting time to 30 seconds and do not spam
                    if "not found" in str(e).lower():
                        logger.info(
                            f"SN{self.SERIAL_NUMBER}: Device not found or probably old BLE: {e}"
                        )
                        waiting_seconds = 30
                    else:
                        logger.warning(f"SN{self.SERIAL_NUMBER}: Unknown exception: {e}")

                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.warning(f"SN{self.SERIAL_NUMBER}: _run task cancelled.")
        except Exception as e:
            logger.exception(f"SN{self.SERIAL_NUMBER}: _run task failed: {e}")
        finally:
            await self._disconnect_gracefully()

    async def _decode_routine(self) -> None:
        """Asynchronously decodes BLE data from the decode queue.

        This runs in parallel with the main connection loop, preventing
        decoding from blocking the event loop when handling multiple connections.
        """
        while not self._stop_event.is_set():
            try:
                # Non-blocking check with timeout to allow graceful shutdown
                try:
                    char_type, data = await asyncio.wait_for(self._decode_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                # Update timestamp for all decodings
                self._data.unix_timestamp = int(time.time() * 1000)

                # Decode based on characteristic type
                if char_type == "std":
                    self._data = PartectorBleDecoderStd.decode(data, data_structure=self._data)
                    logger.debug(f"SN{self.SERIAL_NUMBER}: Decoded std: {data.hex()}")

                elif char_type == "aux":
                    # Check for aux error data
                    if len(data) >= 2 and data[0] == 255 and data[1] == 255:
                        self._data = PartectorBleDecoderAuxError.decode(
                            data, data_structure=self._data
                        )
                    else:
                        self._data = PartectorBleDecoderAux.decode(data, data_structure=self._data)
                    logger.debug(f"SN{self.SERIAL_NUMBER}: Decoded aux: {data.hex()}")

                elif char_type == "size_dist":
                    self._device_type = NaneosDeviceDataPoint.DEV_TYPE_P2PRO
                    self._data = PartectorBleDecoderSize.decode(data, data_structure=self._data)
                    logger.debug(f"SN{self.SERIAL_NUMBER}: Decoded size_dist: {data.hex()}")

            except Exception as e:
                logger.warning(f"SN{self.SERIAL_NUMBER}: Error in decode routine: {e}")

    async def _disconnect_gracefully(self) -> None:
        if not self._client.is_connected:
            return

        try:
            await asyncio.wait_for(self._client.stop_notify(self.CHAR_UUIDS["std"]), timeout=1)
            await asyncio.sleep(0.5)  # wait for windows to free resources
            await asyncio.wait_for(self._client.stop_notify(self.CHAR_UUIDS["aux"]), timeout=1)
            await asyncio.sleep(0.5)  # wait for windows to free resources
            await asyncio.wait_for(
                self._client.stop_notify(self.CHAR_UUIDS["size_dist"]), timeout=1
            )
            await asyncio.sleep(0.5)  # wait for windows to free resources
        except Exception as e:
            logger.debug(f"SN{self.SERIAL_NUMBER}: Failed to stop notify: {e}")

        try:
            await asyncio.wait_for(self._client.disconnect(), timeout=1)
            await asyncio.sleep(0.5)  # wait for windows to free resources
        except Exception as e:
            logger.debug(f"SN{self.SERIAL_NUMBER}: Failed to disconnect: {e}")

    def _disconnect_callback(self, client: BleakClient) -> None:
        """Callback on disconnect."""
        logger.debug(f"SN{self.SERIAL_NUMBER}: Disconnect callback called")

    def _callback_std(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Callback on data received (std characteristic).

        Non-blocking: puts data in decode queue instead of decoding directly.
        Actual decoding happens asynchronously in _decode_routine().
        """
        try:
            self._decode_queue.put_nowait(("std", bytes(data)))
        except asyncio.QueueFull:
            logger.warning(f"SN{self.SERIAL_NUMBER}: Decode queue full, dropping std data")

    def _callback_aux(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Callback on data received (aux characteristic).

        Non-blocking: puts data in decode queue instead of decoding directly.
        Actual decoding happens asynchronously in _decode_routine().
        """
        self._last_aux_data_ts = time.time()
        try:
            self._decode_queue.put_nowait(("aux", bytes(data)))
        except asyncio.QueueFull:
            logger.warning(f"SN{self.SERIAL_NUMBER}: Decode queue full, dropping aux data")

    def _callback_size_dist(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Callback on data received (size_dist characteristic).

        Non-blocking: puts data in decode queue instead of decoding directly.
        Actual decoding happens asynchronously in _decode_routine().
        """
        try:
            self._decode_queue.put_nowait(("size_dist", bytes(data)))
        except asyncio.QueueFull:
            logger.warning(f"SN{self.SERIAL_NUMBER}: Decode queue full, dropping size_dist data")


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
    queue: asyncio.Queue[tuple[BLEDevice, NaneosDeviceDataPoint]],
) -> Optional[dict[int, BLEDevice]]:
    device_dict = {}
    while not queue.empty():
        device, data = await queue.get()
        if data.serial_number:
            device_dict[data.serial_number] = device

    if not device_dict:
        logger.info("No devices found.")
        return None

    return device_dict


async def main_x(x):
    for _ in range(x):
        await main()


if __name__ == "__main__":
    asyncio.run(main_x(3))

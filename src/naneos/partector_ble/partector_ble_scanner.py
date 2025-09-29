from __future__ import annotations

import asyncio
import time

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from naneos.logger import LEVEL_WARNING, get_naneos_logger
from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint
from naneos.partector_ble.decoder.partector_ble_decoder_aux import PartectorBleDecoderAux
from naneos.partector_ble.decoder.partector_ble_decoder_std import PartectorBleDecoderStd
from naneos.partector_ble.partector_ble_decoder import PartectorBleDecoder

logger = get_naneos_logger(__name__, LEVEL_WARNING)


class PartectorBleScanner:
    """
    Context-managed BLE scanner for Partector devices.

    This scanner runs in the provided asyncio event loop and collects advertisement data
    from BLE devices named "P2" or "PartectorBT". Decoded advertisement payloads are
    pushed into an asyncio.Queue for further processing. Can be used with `async with`
    for automatic startup and cleanup.
    """

    SCAN_INTERVAL = 0.8  # seconds
    BLE_NAMES_NANEOS = {"P2", "PartectorBT"}  # P2 on windows, PartectorBT on linux / mac

    # static methods ###############################################################################
    @staticmethod
    def create_scanner_queue() -> asyncio.Queue[tuple[BLEDevice, NaneosDeviceDataPoint]]:
        """Create a queue for the scanner."""
        queue_scanner: asyncio.Queue[tuple[BLEDevice, NaneosDeviceDataPoint]] = asyncio.Queue(
            maxsize=100
        )

        return queue_scanner

    # == Lifecycle and Context Management ==========================================================
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[tuple[BLEDevice, NaneosDeviceDataPoint]],
    ) -> None:
        """
        Initializes the scanner with the given event loop and queue.

        Args:
            loop (asyncio.AbstractEventLoop): The event loop to run the scanner in.
            queue (asyncio.Queue): The queue to store the scanned data.
        """
        self._loop = loop
        self._queue = queue

        self._task: asyncio.Task | None = None

        self._stop_event = asyncio.Event()
        self._stop_event.set()  # stopped by default

    async def __aenter__(self) -> PartectorBleScanner:
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    # == Public Methods ============================================================================
    def start(self) -> None:
        """Starts the scanner."""
        if not self._stop_event.is_set():
            logger.warning("You called PartectorBleScanner.start() but scanner is already running.")
            return

        logger.debug("Starting PartectorBleScanner...")
        self._stop_event.clear()
        self._task = self._loop.create_task(self.scan())

    async def stop(self) -> None:
        """Stops the scanner."""
        logger.debug("Stopping PartectorBleScanner...")
        self._stop_event.set()
        if self._task and not self._task.done():
            await self._task
        logger.info("PartectorBleScanner stopped.")

    # == Internal Async Processing =================================================================
    async def _detection_callback(self, device: BLEDevice, adv: AdvertisementData) -> None:
        """Handles the callbacks from the BleakScanner used in the scan method.

        Args:
            device (BLEDevice): Bleak BLEDevice object
            adv (AdvertisementData): Bleak AdvertisementData object
        """

        if not device.name or device.name not in self.BLE_NAMES_NANEOS:
            return

        adv_data = PartectorBleDecoder.decode_partector_advertisement(adv)
        if not adv_data:
            return

        decoded = PartectorBleDecoderStd.decode(adv_data[0], data_structure=None)
        if not decoded.serial_number:
            return
        if adv_data[1]:
            decoded = PartectorBleDecoderAux.decode(adv_data[1], data_structure=decoded)
        decoded.unix_timestamp = int(time.time()) * 1000
        decoded.connection_type = NaneosDeviceDataPoint.CONN_TYPE_ADVERTISEMENT

        if self._queue.full():  # if the queue is full, make space by removing the oldest item
            await self._queue.get()
        await self._queue.put((device, decoded))

    async def scan(self) -> None:
        """Scans for BLE devices and calls the _detection_callback method for each device found."""

        scanner = BleakScanner(self._detection_callback)

        while not self._stop_event.is_set():
            try:
                async with scanner:
                    await asyncio.sleep(self.SCAN_INTERVAL)
            except Exception as e:
                logger.exception(e)
                await asyncio.sleep(self.SCAN_INTERVAL)  # small backoff before retry

from __future__ import annotations

import asyncio
import time
from collections import deque
from statistics import median

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakDBusError

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

    SCAN_INTERVAL = 0.8  # seconds; backoff before retrying a failed discovery
    BLE_NAMES_NANEOS = {"P2", "PartectorBT"}  # P2 on windows, PartectorBT on linux / mac
    # A device that has not advertised within this window is treated as out of
    # range. Connecting to it would only block the adapter until it times out.
    RSSI_MAX_AGE_SECONDS = 10.0
    RSSI_HISTORY_LEN = 5  # readings kept per device, median is used to damp outliers

    # static methods ###############################################################################
    @staticmethod
    def create_scanner_queue() -> asyncio.Queue[tuple[BLEDevice, NaneosDeviceDataPoint]]:
        """Create a queue for the scanner."""
        # Increased maxsize to 500 to handle bursts from multiple devices
        # Prevents message loss on systems with many concurrent BLE connections
        queue_scanner: asyncio.Queue[tuple[BLEDevice, NaneosDeviceDataPoint]] = asyncio.Queue(
            maxsize=500
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

        # address -> recent (monotonic timestamp, rssi) readings, used to gate
        # connection attempts. A single lucky advertisement is not enough.
        self._rssi: dict[str, deque[tuple[float, int]]] = {}

        # address -> most recently advertised BLEDevice. BlueZ drops devices from
        # its cache, which invalidates older BLEDevice objects, so connections must
        # be able to pick up a fresh one instead of reusing the discovery-time one.
        self._devices: dict[str, BLEDevice] = {}

        self._task: asyncio.Task | None = None

        # True while BlueZ discovery is actually running. The manager uses this
        # instead of probing the adapter with a `bluetoothctl` subprocess: if the
        # adapter goes away, starting discovery is exactly what fails.
        self._discovery_active = False

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

    def get_rssi(self, address: str, max_age_seconds: float | None = None) -> int | None:
        """Returns the recent median RSSI for the given address.

        The median over the last few advertisements is used instead of the latest
        value, because RSSI of a distant device fluctuates heavily and a single
        strong reading is not enough to justify a connection attempt.

        Args:
            address (str): BLE address of the device.
            max_age_seconds (float | None): Only readings younger than this are
                considered. Defaults to RSSI_MAX_AGE_SECONDS.

        Returns:
            The median RSSI in dBm, or None if the device has not advertised
            within max_age_seconds (i.e. it is out of range).
        """
        if max_age_seconds is None:
            max_age_seconds = self.RSSI_MAX_AGE_SECONDS

        history = self._rssi.get(address)
        if not history:
            return None

        now = time.monotonic()
        recent = [rssi for timestamp, rssi in history if now - timestamp <= max_age_seconds]
        if not recent:
            return None

        return int(median(recent))

    @property
    def is_discovering(self) -> bool:
        """True while BlueZ discovery is running, i.e. the adapter is usable."""
        return self._discovery_active and self._bluez_discovery_is_alive()

    @staticmethod
    def _bluez_discovery_is_alive() -> bool:
        """False once BlueZ has stopped scanning underneath us.

        Two ways that happens, both silent. The D-Bus connection bleak holds can
        be dropped, and discovery dies with it. Or the controller itself faults
        ("hci0: hardware error"), and the kernel resets the adapter, which clears
        Discovering. Neither raises: the scan task stays parked on its stop event,
        _discovery_active stays True, and the manager keeps believing discovery is
        running while no advertisement is ever delivered again. bleak rebuilds the
        bus on the next connect attempt but does not restore the discovery, so the
        scanner has to be torn down and started again.

        State is read out of bleak rather than requested: asking bleak for its
        manager reconnects the bus and hides the very failure this looks for.
        """
        try:
            from bleak.backends.bluezdbus import defs
            from bleak.backends.bluezdbus.manager import _global_instances

            manager = _global_instances.get(asyncio.get_running_loop())
            if manager is None:
                return True  # nothing has used the bus yet

            bus = manager._bus
            if bus is None or not bus.connected:
                return False

            adapters = [
                properties[defs.ADAPTER_INTERFACE]
                for properties in manager._properties.values()
                if defs.ADAPTER_INTERFACE in properties
            ]
            if not adapters:
                return True  # no adapter seen yet, nothing to judge

            return any(adapter.get("Discovering", True) for adapter in adapters)
        except Exception:
            # Non-BlueZ backends and bleak internals that moved: never report a
            # dead adapter because this check could not be made.
            return True

    def get_device(self, address: str) -> BLEDevice | None:
        """Returns the most recently advertised BLEDevice for the given address.

        Reconnecting with the BLEDevice from the initial discovery fails once BlueZ
        has evicted the device from its cache ("device ... not found"), so callers
        should refresh the device before every connection attempt.

        Args:
            address (str): BLE address of the device.

        Returns:
            The latest BLEDevice, or None if it has not been seen yet.
        """
        return self._devices.get(address)

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

        history = self._rssi.setdefault(device.address, deque(maxlen=self.RSSI_HISTORY_LEN))
        history.append((time.monotonic(), adv.rssi))
        self._devices[device.address] = device

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

        # Non-blocking put with overflow handling: drop oldest item if queue is full
        # This prevents callbacks from being delayed by queue operations
        try:
            if self._queue.full():
                try:
                    self._queue.get_nowait()  # Remove oldest item
                except asyncio.QueueEmpty:
                    pass
            self._queue.put_nowait((device, decoded))
        except asyncio.QueueFull:
            logger.debug(f"Scanner queue full, dropping advertisement from {device.address}")

    async def scan(self) -> None:
        """Runs BLE discovery until stopped, feeding _detection_callback.

        Discovery is started once and then left running. Re-entering the scanner
        on a timer costs a SetDiscoveryFilter + StartDiscovery + StopDiscovery
        D-Bus round trip per cycle, against the same bluetoothd that carries the
        BLE links, and makes the controller restart its LE scan each time. It is
        also pointless: a running scanner already reports every advertisement,
        so stopping only creates windows in which advertisements are missed.
        """
        while not self._stop_event.is_set():
            try:
                # A fresh scanner per attempt: after a failure the old one may
                # still hold discovery callbacks registered with BlueZ.
                async with BleakScanner(self._detection_callback):
                    self._discovery_active = True
                    await self._stop_event.wait()
            except BleakDBusError as e:
                # Stopping a discovery that BlueZ has already dropped, which is
                # exactly the situation the scanner is restarted for.
                if "No discovery started" in str(e):
                    logger.debug(f"Discovery was already stopped by BlueZ: {e}")
                else:
                    logger.exception(e)
                await asyncio.sleep(self.SCAN_INTERVAL)  # small backoff before retry
            except Exception as e:
                logger.exception(e)
                await asyncio.sleep(self.SCAN_INTERVAL)  # small backoff before retry
            finally:
                self._discovery_active = False

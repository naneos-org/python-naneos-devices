from __future__ import annotations

import asyncio
import sys
import time
from collections import deque
from statistics import median
from typing import Any

from bleak import BleakScanner
from bleak.args.bluez import AdvertisementDataType, BlueZScannerArgs, OrPattern
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakDBusError, BleakError

from naneos.ble.partector.advertisement import PartectorBleDecoder
from naneos.ble.partector.characteristics import PartectorBleDecoderStd
from naneos.logger import get_naneos_logger

logger = get_naneos_logger(__name__)


class PartectorBleScanner:
    """
    Context-managed BLE scanner that discovers Partector devices.

    The scanner exists for the links: it reports which Partector (serial number)
    advertises at which address, keeps the recent RSSI per device for the
    connect gate, and hands out the freshest BLEDevice for reconnects. It does
    not deliver measurement data; that comes from the connections only.

    On Linux it scans passively when BlueZ allows it (bluetoothd started with
    --experimental), which costs no scan requests on the shared antenna of a
    Raspberry Pi. Elsewhere, or when passive scanning is refused, it falls back
    to the usual active scan.
    """

    SCAN_INTERVAL = 0.8  # seconds; backoff before retrying a failed discovery
    BLE_NAMES_NANEOS = {"P2", "PartectorBT"}  # P2 on windows, PartectorBT on linux / mac
    # A device that has not advertised within this window is treated as out of
    # range. Connecting to it would only block the adapter until it times out.
    RSSI_MAX_AGE_SECONDS = 10.0
    RSSI_HISTORY_LEN = 5  # readings kept per device, median is used to damp outliers

    # Passive scanning on BlueZ needs a filter. Partector frames put the protocol
    # byte "X" first in the manufacturer data, and the devices name themselves
    # "P2" (shortened name in the advertisement) or "PartectorBT".
    PASSIVE_PATTERNS = (
        OrPattern(0, AdvertisementDataType.MANUFACTURER_SPECIFIC_DATA, b"X"),
        OrPattern(0, AdvertisementDataType.SHORTENED_LOCAL_NAME, b"P2"),
        OrPattern(0, AdvertisementDataType.COMPLETE_LOCAL_NAME, b"PartectorBT"),
    )

    # static methods ###############################################################################
    @staticmethod
    def create_scanner_queue() -> asyncio.Queue[tuple[BLEDevice, int]]:
        """Queue of (device, serial number) pairs, one per received advertisement."""
        # Bounded: the manager drains it once per second, and a burst from many
        # devices must not grow without limit.
        return asyncio.Queue(maxsize=500)

    @classmethod
    def scanner_kwargs(cls, passive: bool) -> dict[str, Any]:
        """Arguments for BleakScanner: passive with the BlueZ filter, or plain active."""
        if not passive:
            return {}
        return {
            "scanning_mode": "passive",
            "bluez": BlueZScannerArgs(or_patterns=list(cls.PASSIVE_PATTERNS)),
        }

    # == Lifecycle and Context Management ==========================================================
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[tuple[BLEDevice, int]],
    ) -> None:
        """
        Initializes the scanner with the given event loop and queue.

        Args:
            loop (asyncio.AbstractEventLoop): The event loop to run the scanner in.
            queue (asyncio.Queue): Receives (BLEDevice, serial number) per advertisement.
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

        # Passive scanning is tried first on Linux; once BlueZ refuses it, the
        # scanner stays active for the rest of its life.
        self._passive = sys.platform.startswith("linux")

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

    @property
    def is_passive(self) -> bool:
        """True while the scanner runs (or will run) in passive mode."""
        return self._passive

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
        return self._discovery_active and self._bluez_discovery_is_alive(self._passive)

    @staticmethod
    def _bluez_discovery_is_alive(passive: bool) -> bool:
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

        A passive scan is an advertisement monitor, not a discovery, so the
        adapter's Discovering flag stays False; only the bus is judged then.
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

            if passive:
                return True

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
        """Records RSSI and device for a Partector advertisement and reports its serial.

        Args:
            device (BLEDevice): Bleak BLEDevice object
            adv (AdvertisementData): Bleak AdvertisementData object
        """
        # In passive mode the BlueZ filter already selects Partector frames, and
        # the name may be missing; the protocol bytes below are the real check.
        if device.name and device.name not in self.BLE_NAMES_NANEOS:
            return

        adv_data = PartectorBleDecoder.decode_partector_advertisement(adv)
        if not adv_data:
            return

        serial_number = PartectorBleDecoderStd.get_serial_number(adv_data[0])
        if not serial_number:
            return

        history = self._rssi.setdefault(device.address, deque(maxlen=self.RSSI_HISTORY_LEN))
        history.append((time.monotonic(), adv.rssi))
        self._devices[device.address] = device

        # Drop the oldest entry when full: the callback must never block.
        try:
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            self._queue.put_nowait((device, serial_number))
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
                kwargs = self.scanner_kwargs(self._passive)
                async with BleakScanner(self._detection_callback, **kwargs):
                    self._discovery_active = True
                    logger.info(f"BLE scanning ({'passive' if self._passive else 'active'}).")
                    await self._stop_event.wait()
            except BleakDBusError as e:
                if "No discovery started" in str(e):
                    # Stopping a discovery that BlueZ has already dropped, which is
                    # exactly the situation the scanner is restarted for.
                    logger.debug(f"Discovery was already stopped by BlueZ: {e}")
                elif self._passive:
                    self._fall_back_to_active(e)
                else:
                    logger.exception(e)
                await asyncio.sleep(self.SCAN_INTERVAL)  # small backoff before retry
            except BleakError as e:
                if self._passive:
                    self._fall_back_to_active(e)
                else:
                    logger.exception(e)
                await asyncio.sleep(self.SCAN_INTERVAL)
            except Exception as e:
                logger.exception(e)
                await asyncio.sleep(self.SCAN_INTERVAL)  # small backoff before retry
            finally:
                self._discovery_active = False

    def _fall_back_to_active(self, error: Exception) -> None:
        logger.warning(
            f"Passive BLE scanning is not available ({error}); using active scanning. "
            "On Linux, start bluetoothd with --experimental to enable it."
        )
        self._passive = False

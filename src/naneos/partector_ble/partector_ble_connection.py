from __future__ import annotations

import asyncio
import sys
import time
from contextlib import nullcontext
from typing import Callable, Optional

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

# Global lock to prevent concurrent BLE connects on Windows
# Windows BLE stack has race conditions when many devices connect simultaneously.
# On other platforms the lock is skipped: BlueZ serializes connects itself, and
# holding a global lock for the whole connect timeout lets a single unreachable
# device block every healthy device behind it (head-of-line blocking).
_ble_connect_lock = asyncio.Lock()
_SERIALIZE_CONNECTS = sys.platform == "win32"


def _connect_lock():
    """Returns the connect lock on Windows and a no-op context elsewhere."""
    return _ble_connect_lock if _SERIALIZE_CONNECTS else nullcontext()


class PartectorBleConnection:
    # Connect timeout used on every platform. A connect includes GATT service
    # discovery, which regularly needs well over 5s on low power hosts (e.g. a
    # Raspberry Pi Zero 2 W, where WiFi and BLE share a single antenna).
    CONNECT_TIMEOUT_SECONDS = 30

    # Retries are capped at this value so a device can never drop out for minutes.
    MAX_BACKOFF_SECONDS = 30

    # Do not spend a connect attempt on a device whose last advertisement was
    # weaker than this. Attempts on barely reachable devices mostly time out and
    # only push the backoff up for everyone sharing the adapter.
    MIN_RSSI_CONNECT_DBM = -90

    # A device that stops advertising is invisible to the RSSI gate, so the gate
    # alone would keep it from ever being retried. After this long without a
    # usable advertisement, spend one attempt anyway.
    RSSI_GATE_MAX_SILENCE_SECONDS = 120

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
        rssi_provider: Optional[Callable[[], Optional[int]]] = None,
        device_provider: Optional[Callable[[], Optional[BLEDevice]]] = None,
    ) -> None:
        """
        Initializes the BLE connection with the given device, event loop, and queue.

        Args:
            device (BLEDevice): The BLE device to connect to.
            loop (asyncio.AbstractEventLoop): The event loop to run the connection in.
            serial_number (int): The serial number of the device.
            rssi_provider (Callable | None): Optional callable returning the most
                recent RSSI of this device in dBm, or None when it has not been
                advertising recently. Used to skip pointless connect attempts.
                When omitted, every attempt is made regardless of signal strength.
            device_provider (Callable | None): Optional callable returning the most
                recently advertised BLEDevice for this device. Used to refresh a
                stale BLEDevice before reconnecting. When omitted, the device given
                at construction time is reused for every attempt.
        """
        self.SERIAL_NUMBER = serial_number
        self._device_type = NaneosDeviceDataPoint.DEV_TYPE_P2  # Thats the deafault value
        self._data = NaneosDeviceDataPoint()
        self._next_ts = 0.0
        self._queue = queue

        # Multi-characteristic monitoring for disconnection detection
        self._last_std_data_ts = time.time()
        self._last_aux_data_ts = time.time()
        self._last_size_dist_data_ts = time.time()

        # Disconnect detection flag (set by disconnect callback)
        self._disconnected_flag = False

        # Reconnection backoff parameters
        self._reconnect_attempt = 0
        self._max_backoff_seconds = self.MAX_BACKOFF_SECONDS
        self._gatt_error_count = 0  # Track consecutive GATT errors
        self._rssi_provider = rssi_provider
        self._device_provider = device_provider

        # Last time the RSSI gate let a connect attempt through, used to bound
        # how long the gate may keep a device locked out.
        self._last_gate_pass_ts = time.monotonic()

        # Decode queue to decouple decoding from BLE callbacks
        # This prevents blocking the event loop when decoding heavy data
        self._decode_queue: asyncio.Queue = asyncio.Queue(maxsize=200)

        self._device = device
        self._loop = loop
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._stop_event.set()  # stopped by default
        self._client = BleakClient(
            device, self._disconnect_callback, timeout=self.CONNECT_TIMEOUT_SECONDS
        )

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

    @property
    def is_connected(self) -> bool:
        """True while a BLE link to the device is actually established."""
        try:
            return bool(self._client.is_connected)
        except Exception:
            return False

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
                    # Check if disconnected via callback
                    if self._disconnected_flag:
                        logger.info(
                            f"SN{self.SERIAL_NUMBER}: Disconnect detected via callback, reconnecting."
                        )
                        await self._disconnect_gracefully()
                        self._disconnected_flag = False
                        waiting_seconds = self._calculate_backoff()
                        continue

                    # Multi-characteristic timeout detection.
                    # Only meaningful while connected: running these checks during a
                    # backoff wait used to re-trigger the backoff every 60s, so
                    # waiting_seconds could never decay to 0 and the device stayed
                    # unreachable for the rest of the process lifetime.
                    if self._client.is_connected:
                        current_time = time.time()
                        data_timeout = 60  # seconds

                        # Check std characteristic timeout
                        if self._last_std_data_ts + data_timeout < current_time:
                            logger.info(
                                f"SN{self.SERIAL_NUMBER}: No std data for {data_timeout}s, disconnecting."
                            )
                            await self._disconnect_gracefully()
                            self._reset_data_timestamps()
                            waiting_seconds = self._calculate_backoff()
                            continue

                        # Check aux characteristic timeout
                        if self._last_aux_data_ts + data_timeout < current_time:
                            logger.info(
                                f"SN{self.SERIAL_NUMBER}: No aux data for {data_timeout}s, disconnecting."
                            )
                            await self._disconnect_gracefully()
                            self._reset_data_timestamps()
                            waiting_seconds = self._calculate_backoff()
                            continue

                    waiting_seconds = max(0, waiting_seconds - 1)
                    wait = self._next_ts - time.time()
                    if wait > 0:
                        await asyncio.sleep(wait)
                        self._next_ts += 1.0
                    else:
                        if self._client.is_connected:
                            logger.info(f"SN{self.SERIAL_NUMBER}: Waiting time negative: {wait}")
                        self._next_ts = int(time.time()) + 1.0

                    # Data points are published by _emit_data_point() on the
                    # device's own measurement tick, not on this loop's second.
                    if self._client.is_connected:
                        continue

                    if waiting_seconds == 0:
                        if not self._is_signal_strong_enough():
                            self._next_ts = int(time.time()) + 1.0
                            continue

                        await self._refresh_device()

                        # Use global lock to prevent concurrent connections on Windows
                        # This prevents GATT cache race conditions when connecting multiple devices
                        async with _connect_lock():
                            logger.debug(
                                f"SN{self.SERIAL_NUMBER}: Attempting connection with lock..."
                            )
                            await self._client.connect(timeout=self.CONNECT_TIMEOUT_SECONDS)
                            if self._client.is_connected:
                                # Windows needs aggressive delay for GATT service discovery
                                # Base delay is 2.5s + additional per error.
                                # BlueZ already waits for ServicesResolved inside
                                # connect(), so on Linux/macOS this would only be an
                                # idle window in which the fresh link can drop again.
                                if _SERIALIZE_CONNECTS:
                                    discovery_delay = 2.5 + (self._gatt_error_count * 1.0)
                                    discovery_delay = min(discovery_delay, 5.0)
                                    logger.debug(
                                        f"SN{self.SERIAL_NUMBER}: Waiting {discovery_delay:.1f}s for GATT discovery "
                                        f"(error count: {self._gatt_error_count})"
                                    )
                                    await asyncio.sleep(discovery_delay)

                                # Verify GATT services are available before starting notifications
                                if not await self._verify_gatt_services():
                                    logger.warning(
                                        f"SN{self.SERIAL_NUMBER}: GATT services not available after discovery delay."
                                    )
                                    self._gatt_error_count += 1
                                    await self._disconnect_gracefully()
                                    self._disconnected_flag = False

                                    # Recreate client more aggressively (after 1 error for this device)
                                    if self._gatt_error_count >= 1:
                                        logger.info(
                                            f"SN{self.SERIAL_NUMBER}: Recreating BleakClient to clear Windows BLE cache "
                                            f"(GATT errors: {self._gatt_error_count})"
                                        )
                                        self._client = BleakClient(
                                            self._device,
                                            self._disconnect_callback,
                                            timeout=self.CONNECT_TIMEOUT_SECONDS,
                                        )

                                    waiting_seconds = self._calculate_backoff()
                                    continue

                                await self._client.start_notify(
                                    self.CHAR_UUIDS["std"], self._callback_std
                                )
                                await self._client.start_notify(
                                    self.CHAR_UUIDS["aux"], self._callback_aux
                                )
                                await self._client.start_notify(
                                    self.CHAR_UUIDS["size_dist"], self._callback_size_dist
                                )
                                # Reset timestamps and backoff on successful connection
                                self._reset_data_timestamps()
                                self._reconnect_attempt = 0
                                self._disconnected_flag = False
                                self._gatt_error_count = 0  # Reset on success
                        if self._client.is_connected:
                            logger.info(
                                f"SN{self.SERIAL_NUMBER}: Connected to {self._device.address}"
                            )

                    self._next_ts = int(time.time()) + 1.0
                except asyncio.TimeoutError:
                    logger.info(f"SN{self.SERIAL_NUMBER}: Connection timeout.")
                    waiting_seconds = self._calculate_backoff()
                    self._disconnected_flag = False  # already accounted for by the backoff
                    await asyncio.sleep(0.5)
                except BleakDeviceNotFoundError:
                    logger.info(f"SN{self.SERIAL_NUMBER}: Device not found or probably old BLE.")
                    waiting_seconds = self._calculate_backoff()
                    self._disconnected_flag = False  # already accounted for by the backoff
                    await asyncio.sleep(0.5)
                except Exception as e:
                    error_str = str(e).lower()
                    # Check for common BLE errors that need backoff
                    if "not found" in error_str:
                        logger.info(
                            f"SN{self.SERIAL_NUMBER}: Device not found or probably old BLE: {e}"
                        )
                        waiting_seconds = self._calculate_backoff()
                    elif "unreachable" in error_str or "gatt" in error_str:
                        self._gatt_error_count += 1
                        logger.warning(
                            f"SN{self.SERIAL_NUMBER}: GATT/unreachable error #{self._gatt_error_count} "
                            f"(Windows BLE cache issue): {e}"
                        )
                        # Force disconnect to clear state
                        await self._disconnect_gracefully()

                        # Recreate client after repeated GATT errors
                        if self._gatt_error_count >= 2:
                            logger.info(
                                f"SN{self.SERIAL_NUMBER}: Recreating BleakClient after {self._gatt_error_count} "
                                "GATT errors to force Windows cache clear"
                            )
                            self._client = BleakClient(
                                self._device,
                                self._disconnect_callback,
                                timeout=self.CONNECT_TIMEOUT_SECONDS,
                            )

                        waiting_seconds = self._calculate_backoff()
                    else:
                        logger.warning(f"SN{self.SERIAL_NUMBER}: Unknown exception: {e}")
                        # A connect that fails after the link was already up (for
                        # example "failed to discover services, device disconnected")
                        # can leave BlueZ holding a half-open link. The device then
                        # stops advertising, and without an advertisement the RSSI
                        # gate never lets a reconnect through again. Drop the link
                        # and start the next attempt from a fresh client.
                        await self._disconnect_gracefully()
                        self._client = BleakClient(
                            self._device,
                            self._disconnect_callback,
                            timeout=self.CONNECT_TIMEOUT_SECONDS,
                        )
                        waiting_seconds = self._calculate_backoff()

                    # The disconnect callback fires while the connect attempt fails.
                    # Without this the same failure would be counted twice and push
                    # the backoff up at double speed.
                    self._disconnected_flag = False
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.warning(f"SN{self.SERIAL_NUMBER}: _run task cancelled.")
        except Exception as e:
            logger.exception(f"SN{self.SERIAL_NUMBER}: _run task failed: {e}")
        finally:
            await self._disconnect_gracefully()

    def _emit_data_point(self) -> None:
        """Publish the accumulated data point and start the next one.

        Points follow the device's own measurement tick instead of a wall clock
        second. The device sends one std frame per second, but its phase is
        independent of ours: binning those arrivals into fixed one second windows
        left a quarter of the windows empty on a P2 Pro and put two frames into
        as many others, where the first was overwritten before it was ever
        published.
        """
        point = self._data
        self._data = NaneosDeviceDataPoint(
            device_type=self._device_type,
            serial_number=self.SERIAL_NUMBER,
            connection_type=NaneosDeviceDataPoint.CONN_TYPE_CONNECTED,
            # TODO: add firware version from device here
        )

        # A P2 Pro reports number concentration and diameter only together with
        # the size distribution they belong to. That stream runs at 1/6 of the
        # measurement rate, so most points carry neither.
        if self._device_type == NaneosDeviceDataPoint.DEV_TYPE_P2PRO and not any(
            getattr(point, field, None) is not None
            for field in NaneosDeviceDataPoint.BLE_SIZE_DIST_FIELD_NAMES
        ):
            point.particle_number_concentration = None
            point.average_particle_diameter = None

        try:
            self._queue.put_nowait(point)
        except asyncio.QueueFull:
            logger.warning(
                f"SN{self.SERIAL_NUMBER}: Connection queue full, dropping data point."
            )

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
                    # The std frame is the device's measurement tick, so it also
                    # closes the data point.
                    self._emit_data_point()

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

    def _calculate_backoff(self) -> int:
        """Calculate exponential backoff time in seconds.

        Returns:
            Backoff time in seconds (5, 10, 20, then capped at MAX_BACKOFF_SECONDS)
        """
        self._reconnect_attempt += 1
        backoff = min(5 * (2 ** (self._reconnect_attempt - 1)), self._max_backoff_seconds)
        logger.info(
            f"SN{self.SERIAL_NUMBER}: Backoff attempt {self._reconnect_attempt}: {backoff}s"
        )
        return int(backoff)

    async def _refresh_device(self) -> None:
        """Replaces the cached BLEDevice with the most recently advertised one.

        BlueZ removes devices from its cache when they stop advertising for a while.
        Any BLEDevice obtained before that points at a D-Bus path that no longer
        exists, so every following connect fails with "device ... not found" until
        the process is restarted.
        """
        if self._device_provider is None:
            return

        device = self._device_provider()
        if device is None or device is self._device:
            return

        # Never abandon a client that still holds a link: the device only accepts a
        # single connection, so a leaked client would keep the new one from working.
        await self._disconnect_gracefully()

        logger.debug(f"SN{self.SERIAL_NUMBER}: Refreshed BLEDevice before connecting.")
        self._device = device
        self._client = BleakClient(
            device, self._disconnect_callback, timeout=self.CONNECT_TIMEOUT_SECONDS
        )

    def _is_signal_strong_enough(self) -> bool:
        """Check the last advertised RSSI before spending a connect attempt.

        The gate is deliberately not absolute: a device whose link is stuck stops
        advertising, so an unconditional gate would lock it out for the rest of the
        process lifetime. After RSSI_GATE_MAX_SILENCE_SECONDS without a usable
        advertisement one attempt is let through regardless.

        Returns:
            True if no rssi_provider was supplied (behaviour unchanged), if the
            device advertised recently with at least MIN_RSSI_CONNECT_DBM, or if
            the gate has been blocking for too long.
            False if the device is out of range or too weak to connect reliably.
        """
        if self._rssi_provider is None:
            return True

        rssi = self._rssi_provider()

        if rssi is None:
            reason = "No recent advertisement"
        elif rssi < self.MIN_RSSI_CONNECT_DBM:
            reason = f"RSSI {rssi} dBm is below {self.MIN_RSSI_CONNECT_DBM} dBm"
        else:
            self._last_gate_pass_ts = time.monotonic()
            return True

        gated_seconds = time.monotonic() - self._last_gate_pass_ts
        if gated_seconds >= self.RSSI_GATE_MAX_SILENCE_SECONDS:
            logger.info(
                f"SN{self.SERIAL_NUMBER}: {reason}, but gated for {gated_seconds:.0f}s, "
                "attempting connect anyway."
            )
            self._last_gate_pass_ts = time.monotonic()
            return True

        logger.debug(f"SN{self.SERIAL_NUMBER}: {reason}, skipping connect attempt.")
        return False

    def _reset_data_timestamps(self) -> None:
        """Reset all characteristic data timestamps to current time.

        This prevents false disconnection detection after reconnecting.
        """
        current_time = time.time()
        self._last_std_data_ts = current_time
        self._last_aux_data_ts = current_time
        self._last_size_dist_data_ts = current_time

    async def _verify_gatt_services(self) -> bool:
        """Verify that GATT services are available.

        Windows BLE stack sometimes reports connected but services aren't ready.
        This method retries service discovery to work around Windows BLE cache issues.

        Returns:
            True if services are available, False otherwise
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                services = self._client.services
                if services is None:
                    logger.debug(
                        f"SN{self.SERIAL_NUMBER}: Services is None, attempt {attempt + 1}/{max_retries}"
                    )
                    await asyncio.sleep(0.5)
                    continue

                # Check if our service UUID is available
                service = services.get_service(self.SERVICE_UUID)
                if service is None:
                    logger.debug(
                        f"SN{self.SERIAL_NUMBER}: Service UUID not found, attempt {attempt + 1}/{max_retries}"
                    )
                    await asyncio.sleep(0.5)
                    continue

                # Verify all required characteristics are present
                required_chars = ["std", "aux", "size_dist"]
                for char_name in required_chars:
                    char_uuid = self.CHAR_UUIDS[char_name]
                    try:
                        services.get_characteristic(char_uuid)
                    except Exception as e:
                        logger.debug(
                            f"SN{self.SERIAL_NUMBER}: Characteristic {char_name} not found: {e}, "
                            f"attempt {attempt + 1}/{max_retries}"
                        )
                        await asyncio.sleep(0.5)
                        break
                else:
                    # All characteristics found
                    logger.debug(f"SN{self.SERIAL_NUMBER}: All GATT services verified successfully")
                    return True

            except Exception as e:
                logger.debug(
                    f"SN{self.SERIAL_NUMBER}: Error verifying services: {e}, "
                    f"attempt {attempt + 1}/{max_retries}"
                )
                await asyncio.sleep(0.5)

        logger.warning(
            f"SN{self.SERIAL_NUMBER}: GATT service verification failed after {max_retries} attempts"
        )
        return False

    def _disconnect_callback(self, client: BleakClient) -> None:
        """Callback on disconnect.

        Sets the disconnect flag to trigger reconnection in the main loop.
        This ensures we detect disconnections even when is_connected still returns True.
        """
        logger.info(f"SN{self.SERIAL_NUMBER}: Disconnect callback called")
        self._disconnected_flag = True

    def _callback_std(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Callback on data received (std characteristic).

        Non-blocking: puts data in decode queue instead of decoding directly.
        Actual decoding happens asynchronously in _decode_routine().
        """
        self._last_std_data_ts = time.time()
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
        self._last_size_dist_data_ts = time.time()
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

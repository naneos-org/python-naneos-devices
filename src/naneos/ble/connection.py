from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import Callable
from contextlib import nullcontext

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakDeviceNotFoundError, BleakError

from naneos.ble.characteristics import (
    PartectorBleDecoderAux,
    PartectorBleDecoderAuxError,
    PartectorBleDecoderSize,
    PartectorBleDecoderStd,
)
from naneos.data_point import ConnectionType, DeviceType, NaneosDeviceDataPoint
from naneos.logger import get_naneos_logger

logger = get_naneos_logger(__name__)

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

    # A connected device that sent nothing on a characteristic for this long is
    # dropped and reconnected.
    DATA_TIMEOUT_SECONDS = 60

    # Windows only: base delay after connect() before GATT services are trusted,
    # plus one second per previous GATT error, capped.
    WINDOWS_DISCOVERY_DELAY_SECONDS = 2.5
    WINDOWS_DISCOVERY_DELAY_MAX_SECONDS = 5.0

    # Do not spend a connect attempt on a device whose last advertisement was
    # weaker than this. Attempts on barely reachable devices mostly time out and
    # only push the backoff up for everyone sharing the adapter.
    MIN_RSSI_CONNECT_DBM = -85

    # A device that stops advertising is invisible to the RSSI gate, so the gate
    # alone would keep it from ever being retried. After this long without a
    # usable advertisement, spend one attempt anyway.
    RSSI_GATE_MAX_SILENCE_SECONDS = 120

    # Commands: the same ASCII protocol as on USB. A command is written to the
    # "write" characteristic; the answer arrives as an indication on "read" (it
    # cannot be read), in 20 byte frames: the text, "\r\n", padded with spaces.
    # Measured answer times are 0.25 s to 1 s.
    DEVICE_NAMES = {"P2": DeviceType.P2, "P2pro": DeviceType.P2PRO}  # answers to "name?"
    COMMAND_MAX_BYTES = 20
    QUERY_TIMEOUT_SECONDS = 2.0

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
        rssi_provider: Callable[[], int | None] | None = None,
        device_provider: Callable[[], BLEDevice | None] | None = None,
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
        # Unknown until the device reveals it: a size distribution frame means P2 Pro.
        self._device_type: DeviceType | None = None
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

        # One command in flight per device: answers carry no reference to
        # their command, so they are matched by order.
        self._command_lock = asyncio.Lock()
        self._replies: asyncio.Queue[list[str]] = asyncio.Queue()
        self._reply_buffer = b""
        self._commands_available = False
        self._firmware_version: int | None = None
        self._info_task: asyncio.Task | None = None

        self._device = device
        self._loop = loop
        self._task: asyncio.Task | None = None
        self._decode_task: asyncio.Task | None = None
        self._backoff_remaining = 0
        self._stop_event = asyncio.Event()
        self._stop_event.set()  # stopped by default
        self._client = self._new_client()

    async def __aenter__(self) -> PartectorBleConnection:
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    # == Public Methods ============================================================================
    def start(self) -> None:
        """Starts the connection task."""
        if not self._stop_event.is_set():
            logger.warning(f"SN{self.SERIAL_NUMBER}: start() called while already running")
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

    @property
    def device_type(self) -> DeviceType | None:
        """None until the device revealed it (a size distribution frame means P2 Pro)."""
        return self._device_type

    @property
    def firmware_version(self) -> int | None:
        """None until the device answered the query that follows every connect."""
        return self._firmware_version

    async def write(self, command: str) -> None:
        """Send a command that has no answer. Must run on the connection's loop.

        Raises:
            ConnectionError: there is no link, or the device has no command characteristic.
            ValueError: the command does not fit into one write.
        """
        async with self._command_lock:
            await self._write(command)

    async def query(self, command: str, timeout: float | None = None) -> list[str]:
        """Send a command and return the tab separated fields of its answer.

        Raises:
            ConnectionError, ValueError: see write().
            TimeoutError: no answer within timeout.
        """
        async with self._command_lock:
            self._reply_buffer = b""
            while not self._replies.empty():
                self._replies.get_nowait()

            await self._write(command)
            try:
                return await asyncio.wait_for(
                    self._replies.get(), timeout or self.QUERY_TIMEOUT_SECONDS
                )
            except TimeoutError:
                raise TimeoutError(f"SN{self.SERIAL_NUMBER}: no answer to {command!r}.") from None

    async def _write(self, command: str) -> None:
        """Caller holds the command lock."""
        data = command.encode()
        if len(data) > self.COMMAND_MAX_BYTES:
            raise ValueError(f"A BLE command is limited to {self.COMMAND_MAX_BYTES} bytes.")
        if not self.is_connected:
            raise ConnectionError(f"SN{self.SERIAL_NUMBER} is not connected.")
        if not self._commands_available:
            raise ConnectionError(f"SN{self.SERIAL_NUMBER} does not accept commands over BLE.")

        try:
            await self._client.write_gatt_char(self.CHAR_UUIDS["write"], data, response=True)
        except (BleakError, OSError) as e:
            raise ConnectionError(f"SN{self.SERIAL_NUMBER}: write failed: {e}") from e

    async def stop(self) -> None:
        """Stops the connection task and waits for it to disconnect."""
        self._stop_event.set()
        if self._task and not self._task.done():
            await self._task
        logger.info(f"SN{self.SERIAL_NUMBER}: PartectorBleConnection stopped")

    async def _run(self) -> None:
        self._backoff_remaining = 0

        try:
            self._next_ts = int(time.time()) + 1.0
            # Decoding runs in its own task so it never blocks this loop.
            self._decode_task = self._loop.create_task(self._decode_routine())

            while not self._stop_event.is_set():
                try:
                    if await self._watchdog():
                        continue

                    self._backoff_remaining = max(0, self._backoff_remaining - 1)
                    await self._sleep_until_next_tick()

                    # Data points are published by _emit_data_point() on the
                    # device's own measurement tick, not on this loop's second.
                    if self._client.is_connected:
                        continue

                    if self._backoff_remaining == 0:
                        await self._try_connect()

                    self._next_ts = int(time.time()) + 1.0
                except Exception as e:
                    await self._handle_connect_error(e)
        except asyncio.CancelledError:
            logger.warning(f"SN{self.SERIAL_NUMBER}: _run task cancelled.")
        except Exception as e:
            logger.exception(f"SN{self.SERIAL_NUMBER}: _run task failed: {e}")
        finally:
            await self._disconnect_gracefully()
            await self._stop_decode_task()

    async def _watchdog(self) -> bool:
        """Drops a link that the callback reported dead or that stopped sending.

        Returns True if the link was dropped, in which case a backoff has been
        started and the caller should go back to waiting.

        Only meaningful while connected: running the data timeout checks during
        a backoff wait used to re-trigger the backoff every 60s, so the backoff
        could never decay to 0 and the device stayed unreachable for the rest
        of the process lifetime.
        """
        if self._disconnected_flag:
            logger.info(f"SN{self.SERIAL_NUMBER}: Disconnect detected via callback, reconnecting.")
            await self._disconnect_gracefully()
            self._disconnected_flag = False
            self._start_backoff()
            return True

        if not self._client.is_connected:
            return False

        now = time.time()
        for name, last_seen in (("std", self._last_std_data_ts), ("aux", self._last_aux_data_ts)):
            if last_seen + self.DATA_TIMEOUT_SECONDS < now:
                logger.info(
                    f"SN{self.SERIAL_NUMBER}: No {name} data for {self.DATA_TIMEOUT_SECONDS}s, "
                    "disconnecting."
                )
                await self._disconnect_gracefully()
                self._reset_data_timestamps()
                self._start_backoff()
                return True

        return False

    async def _sleep_until_next_tick(self) -> None:
        """Paces the loop at one iteration per second."""
        wait = self._next_ts - time.time()
        if wait > 0:
            await asyncio.sleep(wait)
            self._next_ts += 1.0
        else:
            if self._client.is_connected:
                logger.info(f"SN{self.SERIAL_NUMBER}: Waiting time negative: {wait}")
            self._next_ts = int(time.time()) + 1.0

    async def _try_connect(self) -> None:
        """One connect attempt: RSSI gate, fresh BLEDevice, connect, verify, subscribe.

        Connect errors propagate to _handle_connect_error().
        """
        if not self._is_signal_strong_enough():
            self._next_ts = int(time.time()) + 1.0
            return

        await self._refresh_device()

        # On Windows connects are serialised: its BLE stack has GATT cache
        # races when several devices connect at once.
        async with _connect_lock():
            logger.debug(f"SN{self.SERIAL_NUMBER}: Attempting connection with lock...")
            await self._client.connect()  # the timeout is set on the client
            if not self._client.is_connected:
                return

            if _SERIALIZE_CONNECTS:
                await self._windows_discovery_delay()

            if not await self._verify_gatt_services():
                logger.warning(
                    f"SN{self.SERIAL_NUMBER}: GATT services not available after discovery delay."
                )
                self._gatt_error_count += 1
                await self._disconnect_gracefully()
                self._disconnected_flag = False
                self._recreate_client(
                    f"to clear Windows BLE cache (GATT errors: {self._gatt_error_count})"
                )
                self._start_backoff()
                return

            await self._subscribe()
            # A working link resets every failure counter.
            self._reset_data_timestamps()
            self._reconnect_attempt = 0
            self._disconnected_flag = False
            self._gatt_error_count = 0

        logger.info(f"SN{self.SERIAL_NUMBER}: Connected to {self._device.address}")

    async def _windows_discovery_delay(self) -> None:
        """Windows reports connected before GATT discovery is done; give it time.

        BlueZ already waits for ServicesResolved inside connect(), so on Linux
        and macOS this would only be an idle window in which the fresh link can
        drop again.
        """
        delay = min(
            self.WINDOWS_DISCOVERY_DELAY_SECONDS + self._gatt_error_count,
            self.WINDOWS_DISCOVERY_DELAY_MAX_SECONDS,
        )
        logger.debug(
            f"SN{self.SERIAL_NUMBER}: Waiting {delay:.1f}s for GATT discovery "
            f"(error count: {self._gatt_error_count})"
        )
        await asyncio.sleep(delay)

    async def _subscribe(self) -> None:
        await self._client.start_notify(self.CHAR_UUIDS["std"], self._callback_std)
        await self._client.start_notify(self.CHAR_UUIDS["aux"], self._callback_aux)
        await self._client.start_notify(self.CHAR_UUIDS["size_dist"], self._callback_size_dist)

        # Data flows without it, so a device without the command characteristics
        # is still worth the link.
        try:
            await self._client.start_notify(self.CHAR_UUIDS["read"], self._callback_reply)
            self._commands_available = True
        except Exception as e:
            self._commands_available = False
            logger.info(f"SN{self.SERIAL_NUMBER}: no commands over BLE: {e}")
            return

        if self._firmware_version is None and (self._info_task is None or self._info_task.done()):
            self._info_task = self._loop.create_task(self._read_device_info())

    async def _read_device_info(self) -> None:
        """Ask for what the data frames do not tell: the firmware and the device family.

        Without the name a P2 Pro is only recognised by its first size
        distribution frame, which can take a while.
        """
        try:
            self._firmware_version = int((await self.query("f?"))[0])
            name = (await self.query("name?"))[0]
            if self._device_type is None:
                self._device_type = self.DEVICE_NAMES.get(name)
        except (ConnectionError, TimeoutError, ValueError, IndexError) as e:
            logger.debug(f"SN{self.SERIAL_NUMBER}: could not read the device info: {e}")

    async def _handle_connect_error(self, error: Exception) -> None:
        """Classifies a failed attempt, cleans up and starts the backoff."""
        error_str = str(error).lower()

        if isinstance(error, TimeoutError):
            logger.info(f"SN{self.SERIAL_NUMBER}: Connection timeout.")
        elif isinstance(error, BleakDeviceNotFoundError) or "not found" in error_str:
            logger.info(f"SN{self.SERIAL_NUMBER}: Device not found or probably old BLE: {error}")
        elif "unreachable" in error_str or "gatt" in error_str:
            self._gatt_error_count += 1
            logger.warning(
                f"SN{self.SERIAL_NUMBER}: GATT/unreachable error "
                f"#{self._gatt_error_count} (Windows BLE cache issue): {error}"
            )
            await self._disconnect_gracefully()  # force disconnect to clear state
            if self._gatt_error_count >= 2:
                self._recreate_client(
                    f"after {self._gatt_error_count} GATT errors to force Windows cache clear"
                )
        else:
            logger.warning(f"SN{self.SERIAL_NUMBER}: Unknown exception: {error}")
            # A connect that fails after the link was already up (for example
            # "failed to discover services, device disconnected") can leave
            # BlueZ holding a half-open link. The device then stops advertising,
            # and without an advertisement the RSSI gate never lets a reconnect
            # through again. Drop the link and start from a fresh client.
            await self._disconnect_gracefully()
            self._recreate_client("after an unknown connect error")

        self._start_backoff()
        # The disconnect callback fires while the connect attempt fails.
        # Without this the same failure would be counted twice and push
        # the backoff up at double speed.
        self._disconnected_flag = False
        await asyncio.sleep(0.5)

    def _start_backoff(self) -> None:
        self._backoff_remaining = self._calculate_backoff()

    def _new_client(self) -> BleakClient:
        return BleakClient(
            self._device, self._disconnect_callback, timeout=self.CONNECT_TIMEOUT_SECONDS
        )

    def _recreate_client(self, reason: str) -> None:
        logger.info(f"SN{self.SERIAL_NUMBER}: Recreating BleakClient {reason}")
        self._client = self._new_client()

    async def _stop_decode_task(self) -> None:
        task = self._decode_task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

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
            connection_type=ConnectionType.CONNECTED,
            firmware_version=self._firmware_version,
        )

        # A P2 Pro reports number concentration and diameter only together with
        # the size distribution they belong to. That stream runs at 1/6 of the
        # measurement rate, so most points carry neither.
        if self._device_type == DeviceType.P2PRO and not any(
            getattr(point, field, None) is not None for field in PartectorBleDecoderSize.FIELD_NAMES
        ):
            point.particle_number_concentration = None
            point.average_particle_diameter = None

        try:
            self._queue.put_nowait(point)
        except asyncio.QueueFull:
            logger.warning(f"SN{self.SERIAL_NUMBER}: Connection queue full, dropping data point.")

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
                except TimeoutError:
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
                    if PartectorBleDecoderAuxError.is_error_frame(data):
                        self._data = PartectorBleDecoderAuxError.decode(
                            data, data_structure=self._data
                        )
                    else:
                        self._data = PartectorBleDecoderAux.decode(data, data_structure=self._data)
                    logger.debug(f"SN{self.SERIAL_NUMBER}: Decoded aux: {data.hex()}")

                elif char_type == "size_dist":
                    self._device_type = DeviceType.P2PRO
                    self._data = PartectorBleDecoderSize.decode(data, data_structure=self._data)
                    logger.debug(f"SN{self.SERIAL_NUMBER}: Decoded size_dist: {data.hex()}")

            except Exception as e:
                logger.warning(f"SN{self.SERIAL_NUMBER}: Error in decode routine: {e}")

    async def _disconnect_gracefully(self) -> None:
        if not self._client.is_connected:
            return

        try:
            names = ["std", "aux", "size_dist"] + (["read"] if self._commands_available else [])
            for name in names:
                await asyncio.wait_for(self._client.stop_notify(self.CHAR_UUIDS[name]), timeout=1)
                await self._settle()
        except Exception as e:
            logger.debug(f"SN{self.SERIAL_NUMBER}: Failed to stop notify: {e}")

        try:
            await asyncio.wait_for(self._client.disconnect(), timeout=1)
            await self._settle()
        except Exception as e:
            logger.debug(f"SN{self.SERIAL_NUMBER}: Failed to disconnect: {e}")

    @staticmethod
    async def _settle() -> None:
        """Windows needs a moment to free BLE resources between GATT operations."""
        if _SERIALIZE_CONNECTS:
            await asyncio.sleep(0.5)

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
        self._client = self._new_client()

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
                        f"SN{self.SERIAL_NUMBER}: Services is None, "
                        f"attempt {attempt + 1}/{max_retries}"
                    )
                    await asyncio.sleep(0.5)
                    continue

                # Check if our service UUID is available
                service = services.get_service(self.SERVICE_UUID)
                if service is None:
                    logger.debug(
                        f"SN{self.SERIAL_NUMBER}: Service UUID not found, "
                        f"attempt {attempt + 1}/{max_retries}"
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

    def _callback_reply(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Callback on an answer frame (read characteristic).

        An answer ends with a line end; what follows in that frame is padding.
        """
        self._reply_buffer += bytes(data)
        if b"\n" not in self._reply_buffer:
            return  # a longer answer continues in the next frame

        line = self._reply_buffer.split(b"\n", 1)[0].decode(errors="replace").strip("\r ")
        self._reply_buffer = b""
        self._replies.put_nowait(line.split("\t"))

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

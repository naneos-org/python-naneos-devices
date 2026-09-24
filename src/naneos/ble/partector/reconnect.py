"""When a BLE connection may try again: the backoff after a failure and the RSSI gate.

No I/O in here. The policy only asks the clock and the RSSI provider it is given,
so it is tested without bleak and without an adapter.
"""

import time
from collections.abc import Callable

from naneos.logger import get_naneos_logger

logger = get_naneos_logger(__name__)

# Retries are capped at this value so a device can never drop out for minutes.
MAX_BACKOFF_SECONDS = 30

# Do not spend a connect attempt on a device whose last advertisement was
# weaker than this. Attempts on barely reachable devices mostly time out and
# only push the backoff up for everyone sharing the adapter.
MIN_RSSI_CONNECT_DBM = -85

# A device that stops advertising is invisible to the RSSI gate, so the gate
# alone would keep it from ever being retried. After this long without a
# usable advertisement, spend one attempt anyway.
RSSI_GATE_MAX_SILENCE_SECONDS = 120


class ReconnectPolicy:
    """Exponential backoff, the count of GATT errors and the RSSI gate of one device.

    Args:
        serial_number: only for the log messages.
        rssi_provider: returns the most recent RSSI of the device in dBm, or None when
            it has not been advertising recently. Without it every attempt is allowed.
        clock: monotonic seconds; a test passes its own.
    """

    def __init__(
        self,
        serial_number: int,
        rssi_provider: Callable[[], int | None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._serial_number = serial_number
        self._rssi_provider = rssi_provider
        self._clock = clock

        self.attempt = 0  # failures since the last working link
        self.gatt_errors = 0  # consecutive GATT errors, counted by the caller
        self.backoff_remaining = 0  # seconds of the connection loop to wait

        # Last time the RSSI gate let a connect attempt through, used to bound
        # how long the gate may keep a device locked out.
        self._last_gate_pass = clock()

    @property
    def waiting(self) -> bool:
        """True while the backoff after a failure has not run out."""
        return self.backoff_remaining > 0

    def clear_backoff(self) -> None:
        self.backoff_remaining = 0

    def tick(self) -> None:
        """One second of the connection loop has passed."""
        self.backoff_remaining = max(0, self.backoff_remaining - 1)

    def start_backoff(self) -> None:
        """Count a failed attempt and wait 5, 10, 20 s, then MAX_BACKOFF_SECONDS."""
        self.attempt += 1
        backoff = min(5 * (2 ** (self.attempt - 1)), MAX_BACKOFF_SECONDS)
        logger.info(f"SN{self._serial_number}: Backoff attempt {self.attempt}: {backoff}s")
        self.backoff_remaining = int(backoff)

    def link_established(self) -> None:
        """A working link resets every failure counter."""
        self.attempt = 0
        self.gatt_errors = 0

    def signal_allows_connect(self) -> bool:
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
        elif rssi < MIN_RSSI_CONNECT_DBM:
            reason = f"RSSI {rssi} dBm is below {MIN_RSSI_CONNECT_DBM} dBm"
        else:
            self._last_gate_pass = self._clock()
            return True

        gated_seconds = self._clock() - self._last_gate_pass
        if gated_seconds >= RSSI_GATE_MAX_SILENCE_SECONDS:
            logger.info(
                f"SN{self._serial_number}: {reason}, but gated for {gated_seconds:.0f}s, "
                "attempting connect anyway."
            )
            self._last_gate_pass = self._clock()
            return True

        logger.debug(f"SN{self._serial_number}: {reason}, skipping connect attempt.")
        return False

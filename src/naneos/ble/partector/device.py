"""The thread-safe PartectorDevice handle of a BLE link."""

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

from naneos.ble.partector.connection import PartectorBleConnection
from naneos.data_point import ConnectionType, DeviceType
from naneos.device import NotSupportedError, PartectorDevice

T = TypeVar("T")


class BlePartector(PartectorDevice):
    """A Partector on a BLE link, usable from any thread but the BLE manager's.

    The link lives on the event loop of PartectorBleManager; every call is
    handed over to that loop. The handle stays valid while the manager keeps
    the link, also across reconnects: is_connected tells if it is up right now.
    """

    # On top of the command's own timeout: waiting for the command in flight
    # and for the loop to pick the call up.
    HANDOVER_TIMEOUT_SECONDS = 5.0

    def __init__(self, connection: PartectorBleConnection, loop: asyncio.AbstractEventLoop) -> None:
        self._connection = connection
        self._loop = loop
        self._loop_thread = threading.get_ident()  # created on the loop's thread

    @property
    def serial_number(self) -> int:
        return self._connection.SERIAL_NUMBER

    @property
    def device_type(self) -> DeviceType | None:
        return self._connection.device_type

    @property
    def firmware_version(self) -> int | None:
        return self._connection.firmware_version

    @property
    def connection_type(self) -> ConnectionType:
        return ConnectionType.CONNECTED

    @property
    def is_connected(self) -> bool:
        return self._connection.is_connected

    @property
    def sample_rate_hz(self) -> float:
        return 1

    def write(self, command: str) -> None:
        self._run(self._connection.write(command), PartectorBleConnection.QUERY_TIMEOUT_SECONDS)

    def query(self, command: str, timeout: float | None = None) -> list[str]:
        timeout = timeout or PartectorBleConnection.QUERY_TIMEOUT_SECONDS
        return self._run(self._connection.query(command, timeout), timeout)

    def set_sample_rate(self, hz: int | None) -> None:
        if hz is None:
            return  # 1 Hz is the default over BLE
        raise NotSupportedError(
            "The data rate is fixed at 1 Hz over BLE; it can only be changed over USB."
        )

    def _run(self, coroutine: Coroutine[Any, Any, T], timeout: float) -> T:
        if threading.get_ident() == self._loop_thread:
            coroutine.close()
            raise RuntimeError("A BlePartector cannot be used from the BLE manager's own thread.")
        if self._loop.is_closed():
            coroutine.close()
            raise ConnectionError(f"SN{self.serial_number}: the BLE manager has stopped.")

        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout + self.HANDOVER_TIMEOUT_SECONDS)
        except TimeoutError:
            future.cancel()
            raise

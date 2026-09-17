import asyncio
import warnings

import pytest
from bleak.backends.device import BLEDevice

from naneos.ble.partector.scanner import PartectorBleScanner

pytestmark = pytest.mark.hardware  # needs a Partector on USB or BLE


async def check_queue(queue: asyncio.Queue[tuple[BLEDevice, int]]) -> None:
    if queue.empty():
        warnings.warn("No BLE devices found.", UserWarning, stacklevel=2)

    while not queue.empty():
        device, serial_number = await queue.get()
        assert device is not None
        assert isinstance(serial_number, int) and serial_number > 0


async def async_test_scanner(with_context_manager: bool) -> None:
    """Helper function to test the scanner."""
    loop = asyncio.get_event_loop()
    queue_scanner = PartectorBleScanner.create_scanner_queue()

    if with_context_manager:
        async with PartectorBleScanner(loop=loop, queue=queue_scanner) as scanner:
            await asyncio.sleep(6)  # a few advertising intervals
    else:
        scanner = PartectorBleScanner(loop=loop, queue=queue_scanner)
        scanner.start()
        try:
            await asyncio.sleep(
                6
            )  # a few advertising intervals  # Asynchronous sleep to allow the loop to run
        finally:
            await scanner.stop()

    await check_queue(queue_scanner)


def test_scanner() -> None:
    """Test the scanner functionality."""
    asyncio.run(async_test_scanner(with_context_manager=False))


def test_scanner_with_context_manager() -> None:
    """Test the scanner functionality with context manager."""
    asyncio.run(async_test_scanner(with_context_manager=True))

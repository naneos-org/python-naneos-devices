import asyncio
import warnings

from bleak.backends.device import BLEDevice

from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint
from naneos.partector_ble.partector_ble_scanner import PartectorBleScanner


async def check_queue(
    queue: asyncio.Queue[tuple[BLEDevice, NaneosDeviceDataPoint]],
) -> None:
    if queue.empty():
        warnings.warn("No BLE devices found.", UserWarning)

    # check if there is data in the queue
    while not queue.empty():
        device, data = await queue.get()
        assert device is not None
        assert data is not None
        assert data.serial_number is not None


async def async_test_scanner(with_context_manager: bool) -> None:
    """Helper function to test the scanner."""
    loop = asyncio.get_event_loop()
    queue_scanner = PartectorBleScanner.create_scanner_queue()

    if with_context_manager:
        async with PartectorBleScanner(loop=loop, queue=queue_scanner) as scanner:
            await asyncio.sleep(3)
    else:
        scanner = PartectorBleScanner(loop=loop, queue=queue_scanner)
        scanner.start()
        try:
            await asyncio.sleep(3)  # Asynchronous sleep to allow the loop to run
        finally:
            await scanner.stop()

    await check_queue(queue_scanner)


def test_scanner() -> None:
    """Test the scanner functionality."""
    asyncio.run(async_test_scanner(with_context_manager=False))


def test_scanner_with_context_manager() -> None:
    """Test the scanner functionality with context manager."""
    asyncio.run(async_test_scanner(with_context_manager=True))

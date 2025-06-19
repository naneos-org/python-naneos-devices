import asyncio
from typing import Optional

from bleak.backends.device import BLEDevice

from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint
from naneos.partector_ble.partector_ble_connection import PartectorBleConnection
from naneos.partector_ble.partector_ble_scanner import PartectorBleScanner

SNS = {8617}  # serial numbers to connect to for testing


async def _map_sn_to_device(
    queue: asyncio.Queue[tuple[BLEDevice, NaneosDeviceDataPoint]],
) -> Optional[dict[int, BLEDevice]]:
    device_dict = {}
    while not queue.empty():
        device, data = await queue.get()
        if data.serial_number:
            device_dict[data.serial_number] = device

    if not device_dict:
        return None

    return device_dict


async def async_test_connection(with_context_manager: bool) -> None:
    """Helper function to test the scanner."""
    loop = asyncio.get_event_loop()
    queue_scanner = PartectorBleScanner.create_scanner_queue()
    queue_connection = PartectorBleConnection.create_connection_queue()
    conn_list = []  # serial number to connection mapping

    if with_context_manager:
        async with PartectorBleScanner(loop=loop, queue=queue_scanner) as scanner:
            await asyncio.sleep(5)
    else:
        scanner = PartectorBleScanner(loop=loop, queue=queue_scanner)
        scanner.start()
        try:
            await asyncio.sleep(5)  # Asynchronous sleep to allow the loop to run
        finally:
            await scanner.stop()

    device_dict = await _map_sn_to_device(queue_scanner)
    assert isinstance(device_dict, dict)

    device_dict = {k: v for k, v in device_dict.items() if k in SNS}
    assert len(device_dict) == len(SNS)

    # start connections for all devices
    for serial_number, device in device_dict.items():
        conn_list.append(
            PartectorBleConnection(
                device=device, loop=loop, serial_number=serial_number, queue=queue_connection
            )
        )
        conn_list[-1].start()

    await asyncio.sleep(5)

    # stop connections for all devices
    for conn in conn_list:
        await conn.stop()


def test_connection() -> None:
    """Test the scanner functionality."""
    asyncio.run(async_test_connection(with_context_manager=False))


def test_connection_with_context_manager() -> None:
    """Test the scanner functionality with context manager."""
    asyncio.run(async_test_connection(with_context_manager=True))

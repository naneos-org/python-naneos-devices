import asyncio
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice


async def discover() -> Optional[BLEDevice]:
    device: BLEDevice | None = await BleakScanner.find_device_by_name("P2", timeout=4.0)  # type: ignore

    if isinstance(device, BLEDevice):
        return device

    return None


async def print_client_services(device: BLEDevice) -> None:
    try:
        async with BleakClient(device, timeout=1) as client:
            for service in client.services:
                print(f"[Service] {service}")
                for characteristic in service.characteristics:
                    print(f"[Characteristic] {characteristic}")
    except Exception as e:
        print("Error:", e)


async def find_and_print_services() -> None:
    device: Optional[BLEDevice] = await discover()

    if isinstance(device, BLEDevice):
        print(f"Found device: {device}")
        await print_client_services(device)
    else:
        print("No device found")


if __name__ == "__main__":
    asyncio.run(find_and_print_services())

import asyncio

from bleak import BleakClient, BleakScanner

# Detecting devices
# Connecting devices
# Removing devices when disconnected


async def connect(address):
    async with BleakClient(address) as client:
        for service in client.services:
            print(f"[Service] {service}")

            for characteristic in service.characteristics:
                print(f"[Characteristic] {characteristic}")

                # value = await client.read_gatt_char(characteristic.uuid)
                # print(f"[Value] {value}")


async def discover():
    # filter for device name P2
    device1 = await BleakScanner.find_device_by_name("P2", timeout=4.0)
    await connect(device1.address)
    # print(device1)

    # device2 = await BleakScanner.find_device_by_name("P2", timeout=4.0)
    # print(device2)


async def scan():
    stop_event = asyncio.Event()

    def scanner_callback(device, advertisement_data):
        print(device, advertisement_data)

    # filter for name P2
    async with BleakScanner(scanner_callback) as scanner:
        await stop_event.wait()


if __name__ == "__main__":
    asyncio.run(discover())

import asyncio

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData


def simple_callback(device: BLEDevice, advertisement_data: AdvertisementData):
    if device.name != "P2":
        return

    # save the device for later
    global scanner_ble_device
    scanner_ble_device = device

    print(f"Device: {device.name} ({device.address})")

    # create a bytearray from the manufacturer data key
    tmp = list(advertisement_data.manufacturer_data.keys())[0]
    p2AdvData = bytearray(tmp.to_bytes(2, byteorder="little"))
    # extend the bytearray with the manufacturer data value
    p2AdvData.extend(list(advertisement_data.manufacturer_data.values())[0])

    if len(p2AdvData) > 22:  # that means it has a scan response
        print(chr(p2AdvData[22]))

    sn = int(int(p2AdvData[15]) + (int(p2AdvData[16]) << 8))
    print(f"SN: {sn}")

    ldsa = (
        int(p2AdvData[1]) + (int(p2AdvData[2]) << 8) + (int(p2AdvData[3]) << 16)
    ) / 100.0
    print(f"LDSA: {ldsa}")


async def main():
    scanner = BleakScanner(simple_callback, cb=dict(use_bdaddr=True))

    await scanner.start()
    await asyncio.sleep(2.0)
    await scanner.stop()

    if scanner_ble_device is None:
        print("No device found")
        return

    print(scanner_ble_device.name)

    # connect to device
    async with BleakClient(
        scanner_ble_device, disconnected_callback=(lambda: print("disconnected"))
    ) as client:
        print("connected")

        await client.connect()
        print("connected")

        # get the manufacturer data
        manufacturer_data = await client.read_gatt_char(
            "00002a29-0000-1000-8000-00805f9b34fb"
        )
        print(manufacturer_data)


asyncio.run(main())

import asyncio
import time

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from naneos.partector2.partector1 import Partector1
from naneos.partector2.scan_for_p2 import scan_for_serial_partectors


def simple_callback(device: BLEDevice, advertisement_data: AdvertisementData):
    if device.name != "P2":
        return

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


async def scanBle():
    # BleakScanner that only listens for "P2" devices

    scanner = BleakScanner(simple_callback, cb=dict(use_bdaddr=True))

    await scanner.start()
    await asyncio.sleep(2.0)
    await scanner.stop()


def scanWire():
    devs = scan_for_serial_partectors()
    print(devs)


def readP1():
    devs = scan_for_serial_partectors()
    devs = devs["P1"]
    print(devs)

    p1 = Partector1(list(devs.values())[0])

    time.sleep(5)

    # print(p1.get_data_list())
    print(p1.get_data_pandas())

    p1.close()


if __name__ == "__main__":
    # asyncio.run(scanBle())
    # scanWire()
    readP1()

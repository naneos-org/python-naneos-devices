from threading import Event, Thread
import time
from typing import Optional

import serial
import simplepyble

from naneos.logger import LEVEL_INFO, get_naneos_logger
from naneos.partector_ble.partector_ble_device import PartectorBleDevice

logger = get_naneos_logger(__name__, LEVEL_INFO)


class SimplePyBleWrapper(Thread):
    SERVICE_UUID = "0bd51666-e7cb-469b-8e4d-2742f1ba77cc"
    CHAR_STD = "e7add780-b042-4876-aae1-112855353cc1"
    CHAR_AUX = "e7add781-b042-4876-aae1-112855353cc1"
    CHAR_WRITE = "e7add782-b042-4876-aae1-112855353cc1"
    CHAR_READ = "e7add783-b042-4876-aae1-112855353cc1"
    CHAR_SIZE_DIST = "e7add784-b042-4876-aae1-112855353cc1"

    def __init__(self):
        super().__init__()
        self._event = Event()
        self.initialized = False

        """Dict of all devices that are found in the scan method."""
        # [simplepyble.device, tuple[int, bytearray (advertisement)]]
        self._devices_to_check = {}
        """Dict containing all connected devices, that are in use."""
        self._partector_clients: dict[int, PartectorBleDevice] = {}

        self._adapter = self._init_get_first_adapter()
        if not self._adapter:
            return None

        self.initialized = True
        if self.initialized:
            self.start()

    def stop(self, blocking=True):
        self._event.set()
        if blocking:
            self.join()

    def run(self):
        while not self._event.is_set():
            self._loop_scan()
            self._loop_check_scan()
            time.sleep(1)

    def _init_get_first_adapter(self) -> Optional[simplepyble.Adapter]:
        adapters = simplepyble.Adapter.get_adapters()

        if not adapters:
            logger.error("No BLE adapter found")
            return None

        adapter = adapters[0]
        logger.info(f"Using BLE adapter: {adapter.identifier()}")

        return adapters[0]

    @staticmethod
    def get_full_advertisement(device) -> bytearray:
        adv = device.manufacturer_data()
        adv_0 = next(iter(adv.keys())).to_bytes(2, byteorder="little")
        adv_1 = next(iter(adv.values()))
        adv_bytes = bytearray(adv_0 + adv_1)

        return adv_bytes

    def _loop_scan(self) -> None:
        self._adapter.scan_for(850)

        devices = self._adapter.scan_get_results()

        for device in devices:
            if device.identifier() not in ["P2", "PartectorBT"]:
                continue
            #     logger.info(f"Device: {device.identifier()}")
            advertisement = self.get_full_advertisement(device)
            serial_number = PartectorBleDevice.check_naneos_adv(advertisement)

            if serial_number is None:
                continue

            self._devices_to_check[serial_number] = device

            logger.info(f"Data: {serial_number}")

    def _loop_check_scan(self) -> None:
        for sn, periphereal in self._devices_to_check.items():
            if sn in self._partector_clients:
                continue

            periphereal.connect()

            services = periphereal.services()
            service_characteristic_pair = []
            for service in services:
                for characteristic in service.characteristics():
                    service_characteristic_pair.append((service.uuid(), characteristic.uuid()))

                # for i, (service_uuid, characteristic) in enumerate(service_characteristic_pair):
                #     print(f"{i}: {service_uuid} {characteristic}")

            # logger.info(f"Connected to {sn}")
            contents = periphereal.notify(
                self.SERVICE_UUID, self.CHAR_STD, lambda data: print(data)
            )

            print(contents)


if __name__ == "__main__":
    ble = SimplePyBleWrapper()

    time.sleep(15)
    ble.stop()

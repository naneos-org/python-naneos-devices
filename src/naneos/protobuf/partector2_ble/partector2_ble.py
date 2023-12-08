import asyncio
from datetime import datetime, timezone
from queue import Queue
import subprocess
import sys
from threading import Event, Lock, Thread
import time

from bleak import BleakScanner
import requests

# TODO: refactoring / maybe thread is not needed


class Partector2Ble(Thread):
    def __init__(self) -> None:
        self.__init_thread()
        self.__init_data_structures()

        self.start()

    def __init_thread(self):
        Thread.__init__(self)
        self.name = "ble-partector2"
        self.STOP_EVENT = Event()

    def __init_data_structures(self):
        self.__next_scanning_time = time.time() - 1.0  # starts directly
        self._scanning_data = Queue()
        self._results_dict = {}
        self._results_lock = Lock()

    def run(self):
        print("Starting Partector2 BLE thread")
        asyncio.run(self._main_async())
        print("Closed Partector2 BLE thread and event loop")

    def stop_scanning(self):
        self.STOP_EVENT.set()
        self.join()
        print("Joined Partector2 BLE thread")

    async def _main_async(self):
        await asyncio.gather(self.__scan_in_background(), self.__decode_beacon_data())

    async def __scan_in_background(self):
        while not self.STOP_EVENT.is_set():
            self.__wait_until_trigger()
            self.__update_next_scanning_time()

            # fetching ble readings + saving the timestamp
            tmp_devices = await BleakScanner.discover(timeout=0.8)  # TODO: check timeout
            date_time = datetime.now(tz=timezone.utc)

            for d in (x for x in tmp_devices if x.name == "P2"):
                self._scanning_data.put([date_time, d])

            # handles blueZ error on raspberry pi's (20.11.2021)
            if "linux" in sys.platform:
                self.__clean_bluez_cache()
        print("Stopped scanning")

    def __update_next_scanning_time(self):
        if abs(time.time() - self.__next_scanning_time) < 0.1:
            self.__next_scanning_time += 1.0
        else:
            self.__next_scanning_time = time.time() + 1

    def __wait_until_trigger(self):
        # sleep until the specified datetime
        dt = self.__next_scanning_time - time.time()

        if dt > 0.0 and dt < 1.0:
            time.sleep(dt)

    # method is linux (+ maybe macos) only
    def __clean_bluez_cache(self):
        # get str with all cached devices from shell
        cached_str = subprocess.check_output("bluetoothctl devices", shell=True).decode(
            sys.stdout.encoding
        )

        # str manipulating and removing the apropreate P2 mac-addresses
        cached_list = cached_str.splitlines()
        for line in (x for x in cached_list if "P2" in x):
            # line format: "Device XX:XX:XX:XX:XX:XX P2"
            line = line.replace("Device", "").replace("P2", "").replace(" ", "")
            subprocess.check_output(f"bluetoothctl -- remove {line}", shell=True)

    async def __decode_beacon_data(self):
        while not self.STOP_EVENT.is_set():
            scan_data = list(self._scanning_data.queue)
            self._scanning_data.queue.clear()

            for d in scan_data:
                timestamp = d[0]
                scan_result = d[1]

                beac_meta = scan_result.metadata["manufacturer_data"]
                beac_bytes = list(beac_meta.keys())[0].to_bytes(2, byteorder="little")
                beac_bytes += list(beac_meta.values())[0]

                # if first byte is no X there is something wrong
                if chr(beac_bytes[0]) == "X" and len(beac_bytes) == 22:
                    measurement = self.__parse_mesurment_data(timestamp, beac_bytes)
                    self.__add_measurement_to_results(measurement)

            await asyncio.sleep(3)
        print("Stopped decoding")

    def __parse_mesurment_data(self, timestamp, b: bytes) -> dict:
        """Returns a dict with the serial number as key."""
        serial_number = int(int(b[15]) + (int(b[16]) << 8))
        measurement = {
            "dateTime": timestamp,
            "LDSA": (int(b[1]) + (int(b[2]) << 8) + (int(b[3]) << 16)) / 100.0,
            "diameter": float(int(b[4]) + (int(b[5]) << 8)),
            "number": float(int(b[6]) + (int(b[7]) << 8) + (int(b[8]) << 16)),
            "T": float(int(b[9])),
            "RHcorr": float(int(b[10])),
            "device_status": int(b[11])
            + (int(b[11]) << 8)
            + (((int(b[20]) >> 1) & 0b01111111) << 16),
            "batt_voltage": (int(b[13]) + (int(b[14]) << 8)) / 100.0,
            "particle_mass": (int(b[17]) + (int(b[18]) << 8) + (int(b[19]) << 16)) / 100.0,
        }

        return {serial_number: measurement}

    def __add_measurement_to_results(self, measurement: dict):
        sn, data = list(measurement.items())[0]

        with self._results_lock:
            if sn in list(self._results_dict.keys()):
                self._results_dict[sn].append(data)
            else:
                self._results_dict[sn] = [data]

    def get_and_clear_results(self):
        with self._results_lock:
            results = self._results_dict
            self._results_dict = {}
        return results


def test():
    ble_scanner = Partector2Ble()

    while True:
        try:
            time.sleep(5)
            print("---")
            data = ble_scanner.get_and_clear_results()
            print(data)

        except KeyboardInterrupt:
            break
        except Exception as excep:
            print(f"Excepion during download from P2: {excep}")

    ble_scanner.stop_scanning()
    print("stopped")


if __name__ == "__main__":
    test()

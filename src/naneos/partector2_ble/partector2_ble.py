import asyncio
import subprocess
import sys
import time
from datetime import datetime, timezone
from queue import Queue
from threading import Lock, Thread

from bleak import BleakScanner

from naneos.partector2_ble._lambda_upload import _get_lambda_upload_list_ble
import requests


class Partector2Ble:
    def __init__(self) -> None:
        self.__init_data_structures()
        self.__init_scanning()

    def __init_data_structures(self):
        self.__next_scanning_time = time.time() - 1.0  # starts directly
        self._scanning_data = Queue()
        self._results_dict = {}
        self._results_lock = Lock()

    def __init_scanning(self):
        # Asyncio loop for scanning
        self.__async_loop = asyncio.get_event_loop()
        self.__async_loop.create_task(self.__scan_in_background())
        self.__async_loop.create_task(self.__decode_beacon_data())

        # Run this asyncio loop in a thread in order to not block the main thread
        self.__thread = Thread(target=self.__async_loop.run_forever)
        self.__thread.start()

    def stop_scanning(self):
        self.__async_loop.call_soon_threadsafe(self.__async_loop.stop)
        self.__thread.join()

    async def __scan_in_background(self):
        while True:
            self.__wait_until_trigger()
            self.__update_next_scanning_time()

            # fetching ble readings + saving the timestamp
            tmp_devices = await BleakScanner.discover(
                timeout=0.8
            )  # TODO: check timeout
            date_time = datetime.now(tz=timezone.utc)

            for d in (x for x in tmp_devices if x.name == "P2"):
                self._scanning_data.put([date_time, d])

            # handles blueZ error on raspberry pi's (20.11.2021)
            if "linux" in sys.platform:
                self.__clean_bluez_cache()

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
        while True:
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
            "particle_mass": (int(b[17]) + (int(b[18]) << 8) + (int(b[19]) << 16))
            / 100.0,
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

    def get_lambda_upload_list(self, sn_exclude: list = []) -> list:
        return _get_lambda_upload_list_ble(self.get_and_clear_results(), sn_exclude)


def test():

    ble_scanner = Partector2Ble()

    while True:
        try:
            time.sleep(5)
            print("---")
            data = ble_scanner.get_lambda_upload_list()
            print(data)

            url = (
                "https://hg3zkburji.execute-api.eu-central-1.amazonaws.com/prod/mobile"
            )
            message = {"values": data}
            status_code = requests.post(url=url, json=message)
            print(data)
            print(status_code)
            # data = ble_scanner.get_and_clear_results()
            # print(len(data[8112]))

        except KeyboardInterrupt:
            break
        except Exception as excep:
            print(f"Excepion during download from P2: {excep}")

    ble_scanner.stop_scanning()
    print("stopped")


if __name__ == "__main__":
    test()

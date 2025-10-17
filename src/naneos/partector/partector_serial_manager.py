import threading
import time

import pandas as pd

from naneos.logger import LEVEL_WARNING, get_naneos_logger
from naneos.partector.blueprints._data_structure import NaneosDeviceDataPoint
from naneos.partector.partector1 import Partector1
from naneos.partector.partector2 import Partector2
from naneos.partector.partector2_pro import Partector2Pro
from naneos.partector.scanPartector import scan_for_serial_partectors

logger = get_naneos_logger(__name__, LEVEL_WARNING)


class PartectorSerialManager(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop_event = threading.Event()

        self._data: dict[int, pd.DataFrame] = {}

        self._connected_p1: dict[str, Partector1] = {}
        self._connected_p2: dict[str, Partector2] = {}
        self._connected_p2_pro: dict[str, Partector2Pro] = {}

    def get_data(self) -> dict[int, pd.DataFrame]:
        """Fetches the data from all connected devices and returns it."""
        self._fetch_data()
        data = self._data
        self._data = {}
        return data

    def _fetch_data(self):
        """Returns the data dictionary and deletes it."""
        for port in list(self._connected_p1.keys()):
            points = self._connected_p1[port].get_data()
            for point in points:
                self._data = NaneosDeviceDataPoint.add_data_point_to_dict(self._data, point)

        for port in list(self._connected_p2.keys()):
            points = self._connected_p2[port].get_data()
            for point in points:
                self._data = NaneosDeviceDataPoint.add_data_point_to_dict(self._data, point)

        for port in list(self._connected_p2_pro.keys()):
            points = self._connected_p2_pro[port].get_data()
            for point in points:
                self._data = NaneosDeviceDataPoint.add_data_point_to_dict(self._data, point)

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            self._manager_loop()
        except RuntimeError as e:
            logger.exception(f"SerialManager loop exited with: {e}")

    def get_connected_device_strings(self) -> list[str]:
        """Returns a list of connected device strings."""
        p1_strings = [f"SN{p._sn} (P1)" for port, p in self._connected_p1.items()]
        p2_strings = [f"SN{p._sn} (P2)" for port, p in self._connected_p2.items()]
        p2_pro_strings = [f"SN{p._sn} (P2 Pro)" for port, p in self._connected_p2_pro.items()]

        return p1_strings + p2_strings + p2_pro_strings

    def get_gain_test_activating_devices(self) -> list[int | None]:
        """Returns a list of serial numbers of devices with gain test active."""
        # _wait_with_data_output_until is larger than time.time()
        p2_gain_test = [
            p._sn
            for p in self._connected_p2.values()
            if p._wait_with_data_output_until > time.time()
        ]
        p2_pro_gain_test = [
            p._sn
            for p in self._connected_p2_pro.values()
            if p._wait_with_data_output_until > time.time()
        ]

        return p2_gain_test + p2_pro_gain_test

    def get_connected_addresses(self) -> list[str]:
        p1_ports = list(self._connected_p1.keys())
        p2_ports = list(self._connected_p2.keys())
        p2_pro_ports = list(self._connected_p2_pro.keys())

        return p1_ports + p2_ports + p2_pro_ports

    def get_connected_serial_numbers(self) -> list[int | None]:
        p1_serials = [p._sn for p in self._connected_p1.values()]
        p2_serials = [p._sn for p in self._connected_p2.values()]
        p2_pro_serials = [p._sn for p in self._connected_p2_pro.values()]

        return p1_serials + p2_serials + p2_pro_serials

    def _manager_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                possible_ports = scan_for_serial_partectors(
                    ports_exclude=self.get_connected_addresses()
                )

                self._disconnect_unplugged_ports()
                self._connect_to_new_ports(possible_ports)

                self._fetch_data()  # Fetch data from all connected devices

                time.sleep(1.0)  # Sleep to avoid busy waiting

            except Exception as e:
                logger.exception(f"Error in serial manager loop: {e}")

        self._close_all_ports()

    def _disconnect_unplugged_ports(self) -> None:
        """Disconnects all ports that are not in the possible_ports dictionary."""
        # Disconnect P1 ports
        for port in list(self._connected_p1.keys()):
            if not self._connected_p1[port]._connected:
                self._connected_p1[port].close()
                self._connected_p1.pop(port, None)

        # Disconnect P2 ports
        for port in list(self._connected_p2.keys()):
            if not self._connected_p2[port]._connected:
                self._connected_p2[port].close()
                self._connected_p2.pop(port, None)

        # Disconnect P2 Pro ports
        for port in list(self._connected_p2_pro.keys()):
            if not self._connected_p2_pro[port]._connected:
                print(f"Disconnecting P2 Pro port: {port}")
                self._connected_p2_pro[port].close()
                self._connected_p2_pro.pop(port, None)

    def _connect_to_new_ports(self, possible_ports: dict[str, dict[int, str]]) -> None:
        p1_ports = possible_ports["P1"].values()
        p2_ports = possible_ports["P2"].values()
        p2pro_ports = possible_ports["P2pro"].values()

        for port in p1_ports:
            self._connected_p1[port] = Partector1(port=port)
        for port in p2_ports:
            self._connected_p2[port] = Partector2(port=port)
        for port in p2pro_ports:
            self._connected_p2_pro[port] = Partector2Pro(port=port)

    def _close_all_ports(self) -> None:
        for port in list(self._connected_p1.keys()):
            self._connected_p1[port].close()
            self._connected_p1.pop(port, None)

        for port in list(self._connected_p2.keys()):
            self._connected_p2[port].close()
            self._connected_p2.pop(port, None)

        for port in list(self._connected_p2_pro.keys()):
            self._connected_p2_pro[port].close()
            self._connected_p2_pro.pop(port, None)


if __name__ == "__main__":
    manager = PartectorSerialManager()
    manager.start()

    for _ in range(20):
        time.sleep(10)  # Let the manager run for a while
        data = manager.get_data()

        print(f"Connected ports: {manager.get_connected_addresses()}")
        print(f"Connected serial numbers: {manager.get_connected_serial_numbers()}")
        print("Collected data:")
        print()

        for sn, df in data.items():
            print(f"SN: {sn}")
            print(df)
            print("-" * 40)
            print()

    manager.stop()
    manager.join()

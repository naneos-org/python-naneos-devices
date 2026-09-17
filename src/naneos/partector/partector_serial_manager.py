import threading
import time

import pandas as pd

from naneos.data_point import DeviceType, NaneosDeviceDataPoint
from naneos.device import PartectorDevice
from naneos.frames import add_data_points_to_dict
from naneos.logger import get_naneos_logger
from naneos.partector.blueprints._partector_blueprint import PartectorBlueprint
from naneos.partector.partector1 import Partector1
from naneos.partector.partector2 import Partector2
from naneos.partector.partector2_pro import Partector2Pro
from naneos.partector.scan import FoundDevice, scan_serial_ports

logger = get_naneos_logger(__name__)

DEVICE_CLASSES: dict[DeviceType, type[PartectorBlueprint]] = {
    DeviceType.P1: Partector1,
    DeviceType.P2: Partector2,
    DeviceType.P2PRO: Partector2Pro,
}

DEVICE_LABELS: dict[DeviceType, str] = {
    DeviceType.P1: "P1",
    DeviceType.P2: "P2",
    DeviceType.P2PRO: "P2 Pro",
}


class PartectorSerialManager(threading.Thread):
    """Connects to every Partector on USB, keeps the links alive and collects their data.

    Args:
        gain_test_active: run the electrometer gain test on P2 / P2 Pro. It holds
            the data of a device back for at least 10 s after every connect.
        output_pulse_diagnostics: let P2 / P2 Pro append the pulse diagnostics columns.
    """

    def __init__(
        self, gain_test_active: bool = True, output_pulse_diagnostics: bool = True
    ) -> None:
        super().__init__(daemon=True)
        self._gain_test_active = gain_test_active
        self._output_pulse_diagnostics = output_pulse_diagnostics
        self._stop_event = threading.Event()

        # Written by the manager thread in _fetch_data(), handed over in get_data().
        self._data: dict[int, pd.DataFrame] = {}
        self._data_lock = threading.Lock()

        self._devices: dict[str, PartectorBlueprint] = {}  # key: port

    def get_data(self) -> dict[int, pd.DataFrame]:
        """Returns the data the manager loop collected since the last call.

        The devices are read by the manager thread only (see _fetch_data), so
        this can be called from any thread.
        """
        with self._data_lock:
            data, self._data = self._data, {}
        return data

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            self._manager_loop()
        except RuntimeError as e:
            logger.exception(f"SerialManager loop exited with: {e}")

    def get_connected_device_strings(self) -> list[str]:
        """Human readable list of connected devices, grouped P1, P2, P2 Pro."""
        devices = self._all_devices()
        strings = []
        for kind, label in DEVICE_LABELS.items():
            strings += [f"SN{d.serial_number} ({label})" for d in devices if d.device_type == kind]
        return strings

    def get_gain_test_activating_devices(self) -> list[int | None]:
        """Serial numbers of devices still warming up after a gain test was started."""
        return [d.serial_number for d in self._all_devices() if d.is_settling]

    def get_connected_addresses(self) -> list[str]:
        return list(self._devices.keys())

    def get_connected_serial_numbers(self) -> list[int | None]:
        return [d.serial_number for d in self._all_devices()]

    def get_devices(self) -> list[PartectorDevice]:
        """Handles to write to and query the connected devices and to set their rate."""
        return list(self._all_devices())

    def _all_devices(self) -> list[PartectorBlueprint]:
        """Snapshot of all connected devices, safe to iterate from any thread."""
        return list(self._devices.values())

    def _manager_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                found = scan_serial_ports(ports_exclude=self.get_connected_addresses())

                self._disconnect_unplugged_ports()
                self._connect_to_new_ports(found)

                self._fetch_data()

                time.sleep(1.0)  # Sleep to avoid busy waiting

            except Exception as e:
                logger.exception(f"Error in serial manager loop: {e}")

        self._fetch_data()  # do not lose the last second of data
        self._close_all_ports()

    def _fetch_data(self) -> None:
        """Reads every connected device once. Called from the manager thread only.

        PartectorBlueprint.get_data() is not safe to call concurrently, so
        this must stay the single consumer of the device queues.
        """
        points: list[NaneosDeviceDataPoint] = []
        for device in self._all_devices():
            points.extend(device.get_data())

        if not points:
            return

        with self._data_lock:
            self._data = add_data_points_to_dict(self._data, points)

    def _disconnect_unplugged_ports(self) -> None:
        for port, device in list(self._devices.items()):
            if not device.is_connected:
                logger.info(f"Disconnecting SN{device.serial_number} on {port}")
                device.close()
                self._devices.pop(port, None)

    def _connect_to_new_ports(self, found: list[FoundDevice]) -> None:
        for device in found:
            try:
                self._devices[device.port] = self._connect(device)
            except (ConnectionError, TimeoutError) as e:
                # Found again by the next scan.
                logger.warning(f"Could not connect to SN{device.serial_number}: {e}")

    def _connect(self, found: FoundDevice) -> PartectorBlueprint:
        if found.kind == DeviceType.P1:
            return Partector1(port=found.port)
        cls = Partector2Pro if found.kind == DeviceType.P2PRO else Partector2
        return cls(
            port=found.port,
            gain_test_active=self._gain_test_active,
            output_pulse_diagnostics=self._output_pulse_diagnostics,
        )

    def _close_all_ports(self) -> None:
        for port, device in list(self._devices.items()):
            device.close()
            self._devices.pop(port, None)

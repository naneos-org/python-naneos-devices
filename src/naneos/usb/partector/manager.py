import threading
import time

import pandas as pd

from naneos.data_point import DeviceType, NaneosDeviceDataPoint, PointListener
from naneos.device import NotSupportedError, PartectorDevice
from naneos.frames import add_data_points_to_dict
from naneos.logger import get_naneos_logger
from naneos.usb.partector.device import (
    Partector1,
    Partector2,
    Partector2Family,
    Partector2Pro,
    UsbPartector,
)
from naneos.usb.partector.scan import FoundDevice, scan_serial_ports

logger = get_naneos_logger(__name__)

DEVICE_CLASSES: dict[DeviceType, type[UsbPartector]] = {
    DeviceType.P1: Partector1,
    DeviceType.P2: Partector2,
    DeviceType.P2PRO: Partector2Pro,
}


class PartectorSerialManager(threading.Thread):
    """Connects to every Partector on USB, keeps the links alive and collects their data.

    Args:
        gain_test_active: run the electrometer gain test on P2 / P2 Pro. It holds
            the data of a device back for at least 10 s after every connect.
        output_pulse_diagnostics: let P2 / P2 Pro append the pulse diagnostics columns.
        point_listener: called with every data point as it arrives, in addition to
            get_data(). Runs on the reader threads: must be quick and must not block.
        sample_rate_hz: the data rate of every device, see the property.
    """

    def __init__(
        self,
        gain_test_active: bool = True,
        output_pulse_diagnostics: bool = True,
        point_listener: PointListener | None = None,
        sample_rate_hz: int | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self._point_listener = point_listener
        self._gain_test_active = gain_test_active
        self._output_pulse_diagnostics = output_pulse_diagnostics
        self._sample_rate_hz = self.check_sample_rate(sample_rate_hz)
        self._sample_rate_changed = threading.Event()
        self._stop_event = threading.Event()

        # Written by the manager thread in _fetch_data(), handed over in get_data().
        self._data: dict[int, pd.DataFrame] = {}
        self._data_lock = threading.Lock()

        self._devices: dict[str, UsbPartector] = {}  # key: port

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

    @property
    def sample_rate_hz(self) -> int | None:
        """The data rate of every device: 1, 10 or 100 Hz, or None for the default
        of each device (1 Hz, size distribution mode on a P2 Pro). Setting it
        changes the connected devices within a second and applies to the ones
        that connect later.
        """
        return self._sample_rate_hz

    @sample_rate_hz.setter
    def sample_rate_hz(self, hz: int | None) -> None:
        self._sample_rate_hz = self.check_sample_rate(hz)
        self._sample_rate_changed.set()  # applied by the manager thread

    @staticmethod
    def check_sample_rate(hz: int | None) -> int | None:
        # The rates a device takes, without 0: that switches one device off.
        rates = sorted(rate for rate in UsbPartector.SAMPLE_RATE_CODES if rate)
        if hz is not None and hz not in rates:
            raise ValueError(f"Sample rate must be one of {rates} Hz, or None for the default.")
        return hz

    def run(self) -> None:
        try:
            self._manager_loop()
        except RuntimeError as e:
            logger.exception(f"SerialManager loop exited with: {e}")

    def get_settling_serial_numbers(self) -> list[int | None]:
        """Serial numbers of devices still warming up after a gain test was started."""
        return [d.serial_number for d in self._all_devices() if d.is_settling]

    def get_connected_serial_numbers(self) -> list[int | None]:
        return [d.serial_number for d in self._all_devices()]

    def get_devices(self) -> list[PartectorDevice]:
        """Handles to write to and query the connected devices and to set their rate."""
        return list(self._all_devices())

    def _all_devices(self) -> list[UsbPartector]:
        """Snapshot of all connected devices, safe to iterate from any thread."""
        return list(self._devices.values())

    def _manager_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                found = scan_serial_ports(ports_exclude=list(self._devices))

                self._disconnect_unplugged_ports()
                self._apply_sample_rate()  # before the connect: a new device gets the rate itself
                self._connect_to_new_ports(found)

                self._fetch_data()

                time.sleep(1.0)  # Sleep to avoid busy waiting

            except Exception as e:
                logger.exception(f"Error in serial manager loop: {e}")

        self._fetch_data()  # do not lose the last second of data
        self._close_all_ports()

    def _fetch_data(self) -> None:
        """Reads every connected device once. Called from the manager thread only.

        UsbPartector.get_data() is not safe to call concurrently, so
        this must stay the single consumer of the device queues.
        """
        points: list[NaneosDeviceDataPoint] = []
        for device in self._all_devices():
            points.extend(device.get_data())

        if not points:
            return

        with self._data_lock:
            self._data = add_data_points_to_dict(self._data, points)

    def _apply_sample_rate(self) -> None:
        if not self._sample_rate_changed.is_set():
            return
        self._sample_rate_changed.clear()
        for device in self._all_devices():
            try:
                device.set_sample_rate(self._sample_rate_hz)
            except (ConnectionError, NotSupportedError) as e:
                logger.warning(f"SN{device.serial_number}: could not set the sample rate: {e}")

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

    def _connect(self, found: FoundDevice) -> UsbPartector:
        cls = DEVICE_CLASSES[found.kind]
        if issubclass(cls, Partector2Family):
            return cls(
                port=found.port,
                sample_rate_hz=self._sample_rate_hz,
                gain_test_active=self._gain_test_active,
                output_pulse_diagnostics=self._output_pulse_diagnostics,
                point_listener=self._point_listener,
            )
        return cls(
            port=found.port,
            sample_rate_hz=self._sample_rate_hz,
            point_listener=self._point_listener,
        )

    def _close_all_ports(self) -> None:
        for port, device in list(self._devices.items()):
            device.close()
            self._devices.pop(port, None)

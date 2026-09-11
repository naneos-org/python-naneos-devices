"""naneos-devices: talk to naneos particle solutions devices over serial and BLE."""

from importlib.metadata import PackageNotFoundError, version

from naneos.data_point import ConnectionType, DeviceType, NaneosDeviceDataPoint
from naneos.iotweb.naneos_upload_thread import NaneosUploadThread
from naneos.logger import enable_console_logging, enable_file_logging
from naneos.manager.naneos_device_manager import NaneosDeviceManager
from naneos.partector.partector_serial_manager import PartectorSerialManager
from naneos.partector_ble.partector_ble_manager import PartectorBleManager

try:
    __version__ = version("naneos-devices")
except PackageNotFoundError:  # running from a checkout without an installed dist
    __version__ = "0.0.0"

__all__ = [
    "__version__",
    "ConnectionType",
    "DeviceType",
    "NaneosDeviceDataPoint",
    "NaneosDeviceManager",
    "NaneosUploadThread",
    "PartectorBleManager",
    "PartectorSerialManager",
    "enable_console_logging",
    "enable_file_logging",
]

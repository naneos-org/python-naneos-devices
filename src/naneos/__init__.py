"""naneos-devices: talk to naneos particle solutions devices over serial and BLE."""

from importlib.metadata import PackageNotFoundError, version

from naneos.ble.partector.manager import PartectorBleManager
from naneos.cloud.upload import upload_snapshot
from naneos.data_point import ConnectionType, DeviceType, NaneosDeviceDataPoint
from naneos.device import NotSupportedError, PartectorDevice
from naneos.diagnostics import PulseForm, UiCurve
from naneos.logger import enable_console_logging, enable_file_logging
from naneos.manager import NaneosDeviceManager
from naneos.usb.partector.manager import PartectorSerialManager

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
    "NotSupportedError",
    "PartectorBleManager",
    "PartectorDevice",
    "PartectorSerialManager",
    "PulseForm",
    "UiCurve",
    "enable_console_logging",
    "enable_file_logging",
    "upload_snapshot",
]

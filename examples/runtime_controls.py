"""Change the manager while it runs: transports, upload and the gathering interval.

Usage: python runtime_controls.py
"""

import time

from naneos import NaneosDeviceManager, enable_console_logging
from naneos.logger import LEVEL_INFO


def show(manager: NaneosDeviceManager) -> None:
    print(
        f"serial={manager.use_serial} ble={manager.use_ble} upload={manager.upload_active} "
        f"interval={manager.gathering_interval_seconds}s devices={manager.get_devices()}"
    )


def main() -> None:
    enable_console_logging(LEVEL_INFO)

    manager = NaneosDeviceManager(use_ble=False, upload_active=False)
    manager.start()
    time.sleep(10)
    show(manager)

    manager.use_ble = True  # takes effect within a second
    manager.gathering_interval_seconds = 45  # clamped to 10-600 s
    time.sleep(20)
    show(manager)

    manager.use_serial = False  # the USB devices are released, BLE takes over
    time.sleep(10)
    show(manager)

    manager.stop()
    manager.join()


if __name__ == "__main__":
    main()

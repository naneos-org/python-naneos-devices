"""Fire and forget: upload the data of every Partector in reach to the naneos IoT service.

Usage: python quick_start.py        (stop with Ctrl+C)
"""

import time

from naneos import NaneosDeviceManager, enable_console_logging
from naneos.logger import LEVEL_INFO


def main() -> None:
    enable_console_logging(LEVEL_INFO)  # the library is silent by default

    manager = NaneosDeviceManager(
        use_serial=True,
        use_ble=True,
        upload_active=True,
        gathering_interval_seconds=30,  # clamped to [10, 600]
        ble_serial_numbers=None,  # or e.g. [8617, 8764] to link only to your own devices
    )
    manager.start()

    try:
        while True:
            time.sleep(manager.seconds_until_next_snapshot + 1)

            for device in manager.get_devices():
                print(device)  # e.g. <Partector2 SN8617 P2 serial>
            print()
    except KeyboardInterrupt:
        pass

    manager.stop()
    manager.join()
    print("Stopped.")


if __name__ == "__main__":
    main()

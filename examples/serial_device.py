"""Scan the USB ports, connect to the first Partector found and print its data.

Usage: python serial_device.py
"""

import time

import pandas as pd

from naneos.frames import add_data_points_to_dict
from naneos.logger import LEVEL_INFO, enable_console_logging
from naneos.partector.partector_serial_manager import DEVICE_CLASSES
from naneos.partector.scan import scan_serial_ports


def main() -> None:
    enable_console_logging(LEVEL_INFO)

    found = scan_serial_ports()
    print("Found:", found)
    if not found:
        return

    first = found[0]
    device = DEVICE_CLASSES[first.kind](port=first.port)

    data: dict[int, pd.DataFrame] = {}
    try:
        for _ in range(5):
            time.sleep(3)
            data = add_data_points_to_dict(data, device.get_data())
            df = next(iter(data.values()), pd.DataFrame())
            if not df.empty:
                print(f"SN{first.serial_number} on {first.port}")
                print(df.dropna(axis=1, how="all"))
                break
            print("No data received yet...")
    finally:
        device.close(blocking=True)


if __name__ == "__main__":
    main()

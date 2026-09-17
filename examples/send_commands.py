"""Send the commands of a text file line by line to a Partector on USB or BLE.

Usage: python send_commands.py <serial_number> <commands_file>

Only lines starting with "2" are sent, one every 100 ms. The device is used over
USB if it is plugged in, otherwise over BLE, where a command is limited to 20 bytes.
"""

import sys
import time

from naneos import NaneosDeviceManager, PartectorDevice
from naneos.logger import LEVEL_INFO, enable_console_logging

CONNECT_TIMEOUT_SECONDS = 60


def wait_for_device(manager: NaneosDeviceManager, serial_number: int) -> PartectorDevice:
    deadline = time.time() + CONNECT_TIMEOUT_SECONDS
    while time.time() < deadline:
        try:
            return manager.get_device(serial_number)
        except KeyError:
            time.sleep(1)
    raise ValueError(f"Device with serial number {serial_number} not found.")


def send_commands_to_device(serial_number: int, commands_path: str) -> None:
    manager = NaneosDeviceManager(upload_active=False, ble_serial_numbers=[serial_number])
    manager.start()

    try:
        device = wait_for_device(manager, serial_number)
        print(f"Sending to {device}")

        with open(commands_path) as f:
            for line in f:
                if line.startswith("2"):
                    device.write(line.strip())
                    time.sleep(0.1)
    finally:
        manager.stop()
        manager.join()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    enable_console_logging(LEVEL_INFO)
    send_commands_to_device(int(sys.argv[1]), sys.argv[2])

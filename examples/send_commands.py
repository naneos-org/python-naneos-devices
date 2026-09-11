"""Send the commands of a text file line by line to a Partector on USB.

Usage: python send_commands.py <serial_number> <commands_file>

Only lines starting with "2" are sent, one every 100 ms.
"""

import sys
import time

import serial

from naneos.partector.scan import scan_for_serial_partector


def send_commands_to_device(serial_number: int, commands_path: str) -> None:
    port = scan_for_serial_partector(serial_number)
    if port is None:
        raise ValueError(f"Device with serial number {serial_number} not found.")

    with serial.Serial(port, baudrate=9600, timeout=1) as ser:
        ser.flush()
        ser.write(b"!")  # clear device buffer
        time.sleep(1)

        with open(commands_path) as f:
            for line in f:
                if line.startswith("2"):
                    ser.write(line.encode())
                    time.sleep(0.1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    send_commands_to_device(int(sys.argv[1]), sys.argv[2])

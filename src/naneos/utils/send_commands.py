import time

import serial

from naneos.partector.scanPartector import scan_for_serial_partectors


### Utility to send commands from a commands file to a device via serial connection.
def send_commands_to_device(serial_number: int, commands_path: str) -> None:
    scan_result = scan_for_serial_partectors()
    scan_result = {k: v for x in scan_result.values() for (k, v) in x.items()}  #

    if serial_number not in scan_result:
        raise ValueError(f"Device with serial number {serial_number} not found.")
    port = scan_result[serial_number]

    with serial.Serial(port, baudrate=9600, timeout=1) as ser:
        ser.flush()
        ser.write(b"!")  # clear device buffer
        time.sleep(1)  # wait a bit

        with open(commands_path, "r") as f:
            for line in f:
                if line.startswith("2"):
                    ser.write(line.encode())
                    time.sleep(0.1)  # slight delay between commands


if __name__ == "__main__":
    send_commands_to_device(8617, "/Users/huegi/Downloads/commandsSN8617.txt")

from pathlib import Path
import sys

import serial


def list_serial_ports() -> list[str]:
    """Returns a list of serial ports available on the system.

    Raises:
        OSError: If the platform is not supported.

    Returns:
        list[str]: A list of serial ports available on the system.
    """
    ports: list[str] = _get_all_open_ports()
    ports = _check_port_function(ports)

    return ports


def _get_all_open_ports() -> list[str]:
    ports: list[str] = []

    if sys.platform.startswith("win"):
        ports = ["COM%s" % (i + 1) for i in range(256)]
    elif sys.platform.startswith("linux") or sys.platform.startswith("cygwin"):
        ports = [str(port) for port in Path("/dev").glob("tty[A-Za-z]*")]
    elif sys.platform.startswith("darwin"):  # mac
        ports = [str(port) for port in Path("/dev").glob("tty.*") if "Bluetooth" not in str(port)]
    else:
        raise OSError(f"Unsupported platform: {sys.platform}")

    return ports


def _check_port_function(ports: list[str]) -> list[str]:
    working_ports: list[str] = []

    for port in ports:
        for _ in range(100):  # I have to do this because of windows and P2's 100Hz output
            try:
                s = serial.Serial(port)
                s.write("X0000!".encode())
                s.close()
                working_ports.append(port)
                break
            except (OSError, serial.SerialException):
                pass

    return working_ports

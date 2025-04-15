import sys
from pathlib import Path

import serial
import serial.tools.list_ports as ls


def list_serial_ports(ports_exclude: list = []) -> list[str]:
    """Returns a list of serial ports available on the system.

    Raises:
        OSError: If the platform is not supported.

    Returns:
        list[str]: A list of serial ports available on the system.
    """
    # ports: list[str] = _get_all_open_ports()
    ports: list[str] = _get_all_dosemet_ports(ports_exclude)
    ports = _check_port_function(ports)

    return ports


def _get_all_dosemet_ports(ports_exclude: list) -> list[str]:
    ports: list[str] = []

    all_ports = ls.comports()
    all_ports = [port for port in all_ports if port.device not in ports_exclude]
    for port in all_ports:
        if (port.pid == 5 and port.vid == 65535) or (
            port.serial_number and "dosemet" in port.serial_number.lower()
        ):
            ports.append(port.device)

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
                s.write(b"X0000!")
                s.close()
                working_ports.append(port)
                break
            except (OSError, serial.SerialException):
                pass

    return working_ports

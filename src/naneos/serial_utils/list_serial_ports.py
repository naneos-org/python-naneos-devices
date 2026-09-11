import serial
import serial.tools.list_ports as ls

# USB identifiers of the Partector serial interface.
_PARTECTOR_VID = 65535
_PARTECTOR_PID = 5

# A P2 streaming at 100 Hz can make the open() on Windows fail transiently,
# so a port is only given up after this many immediate retries.
PORT_OPEN_RETRIES = 100


def list_serial_ports(ports_exclude: list[str] | None = None) -> list[str]:
    """Serial ports with a Partector behind them, excluding ports_exclude."""
    ports = _get_all_partector_ports(ports_exclude or [])
    return _check_port_function(ports)


def _get_all_partector_ports(ports_exclude: list[str]) -> list[str]:
    return [
        port.device
        for port in ls.comports()
        if port.device not in ports_exclude
        and (
            (port.pid == _PARTECTOR_PID and port.vid == _PARTECTOR_VID)
            or (port.serial_number and "dosemet" in port.serial_number.lower())
        )
    ]


def _check_port_function(ports: list[str]) -> list[str]:
    """Keep only the ports that can be opened and written to."""
    working_ports: list[str] = []

    for port in ports:
        for _ in range(PORT_OPEN_RETRIES):
            try:
                s = serial.Serial(port)
                s.write(b"X0000!")
                s.close()
                working_ports.append(port)
                break
            except (OSError, serial.SerialException):
                pass

    return working_ports

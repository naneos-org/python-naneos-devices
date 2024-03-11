from naneos.serial_utils import list_serial_ports


def test_check_serial_connection() -> None:
    """Test if the serial connection is working."""
    ports: list[str] = list_serial_ports()
    assert len(ports) > 0, "It seems you have no device connected to your computer."

class PartectorDefaults:
    """Default values for the Partector when connected via serial port."""

    SERIAL_RETRIES = 7
    SERIAL_TIMEOUT = 0.2
    SERIAL_TIMEOUT_INFO = SERIAL_TIMEOUT + 0.05
    SERIAL_BAUDRATE = 115200
    SERIAL_QUEUE_MAXSIZE = 200
    SERIAL_INFO_QUEUE_MAXSIZE = 20

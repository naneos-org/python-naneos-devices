"""Compatibility module: the scanner moved to naneos.partector.scan."""

from naneos.partector.scan import (  # noqa: F401
    FoundDevice,
    ScanPartector,
    scan_for_serial_partector,
    scan_for_serial_partectors,
    scan_serial_ports,
)

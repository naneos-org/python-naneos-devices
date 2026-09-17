"""Devices on USB: the shared serial transport, and one subpackage per device family."""

from naneos.usb.partector import PartectorSerialManager

__all__ = ["PartectorSerialManager"]

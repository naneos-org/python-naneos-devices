# naneos-devices

Python package to read naneos particle solutions devices (Partector 1, Partector 2,
Partector 2 Pro) over USB and Bluetooth Low Energy, gather the measurements as pandas
DataFrames and optionally upload them to the naneos IoT service.

Start with the [README on GitHub](https://github.com/naneos-org/python-naneos-devices): it
explains the device manager, which is all most applications need, and links the examples.

## User guide

* [Devices and commands](user-guide/devices.md): device handles, data rate, Partector 2 Pro modes.
* [Desktop App (Tray Icon)](user-guide/desktop-app.md): Windows, macOS and Linux computers as uploaders, one command to install.
* [Raspberry Pi Setup](user-guide/raspberry-pi-setup.md): a Pi as an always-on uploader.
* [Logging](user-guide/logging.md)
* [Migrating from 1.x to 2.0](user-guide/migration-2.0.md)

## Development

* [Development](development/contributing.md): tests, hardware testing before a merge, protobuf,
  building executables.
* The API Reference section is generated from the source code.

## Build this documentation locally

* `uv run mkdocs serve` - Start the live-reloading docs server.
* `uv run mkdocs build` - Build the documentation site.

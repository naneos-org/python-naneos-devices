# naneos-devices


[![GitHub Issues][gh-issues]](https://github.com/naneos-org/python-naneos-devices/issues)
[![GitHub Pull Requests][gh-pull-requests]](https://github.com/naneos-org/python-naneos-devices/pulls)
[![Ruff][ruff-badge]](https://github.com/astral-sh/ruff)
[![License][mit-license]](LICENSE.txt)

<!-- hyperlinks -->
[gh-issues]: https://img.shields.io/github/issues/naneos-org/python-naneos-devices
[gh-pull-requests]: https://img.shields.io/github/issues-pr/naneos-org/python-naneos-devices
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[mit-license]: https://img.shields.io/badge/license-MIT-blue.svg
<!-- hyperlinks -->

[![Projektlogo](https://raw.githubusercontent.com/naneos-org/public-data/master/img/logo_naneos.png)](https://naneos.ch)

This repository contains a collection of Python scripts and utilities for our [naneos particle solutions](https://naneos.ch) measurement devices. These scripts will provide various functionalities related to data acquisition, analysis, and visualization for your measurement devices.

# Installation

You can install the `naneos-devices` package using pip. Make sure you have Python 3.11 or higher installed. Open a terminal and run the following command:

```bash
pip install naneos-devices
```

# Usage

## Naneos Device Manager
NaneosDeviceManager is a tiny, fire-and-forget thread that auto-manages Naneos devices over Serial and BLE, periodically gathers data, and (optionally) uploads it.
You can enable/disable transports at construction time and at runtime, adjust the gathering interval, and/or pipe data into your own code via a user-provided queue.Queue.
Clean start/stop APIs make integration trivial.

**Highlights**
- ✅ Easy on/off switches for Serial and BLE (before or during runtime)
- ⏱️ Configurable gathering interval (clamped to 10–600 s)
- 📤 Optional auto-upload (enable/disable anytime)
- 📦 Queue hand-off: receive dict[int, pandas.DataFrame] snapshots and process them in your app
- 🧵 Daemon thread with graceful shutdown

### Quick Start (fire and forget upload from all devices in reach to naneos IoT service)
```python
import time

from naneos.manager import NaneosDeviceManager

manager = NaneosDeviceManager(
    use_serial=True,
    use_ble=True,
    upload_active=True,
    gathering_interval_seconds=30,  # clamped to [10, 600]
)
manager.start()

try:
    while True:
        remaining = manager.get_seconds_until_next_upload()
        print(f"Next upload in: {remaining:.0f}s")
        time.sleep(remaining + 1)

        print("Serial:", manager.get_connected_serial_devices())
        print("BLE   :", manager.get_connected_ble_devices())
        print()
except KeyboardInterrupt:
    pass

manager.stop()
manager.join()
print("Stopped.")
```

### Runtime Controls (toggle anytime during execution)
```python
# Turn Serial on/off during runtime
manager.use_serial_connections(True)  # or False
print("Serial enabled:", manager.get_serial_connection_status())

# Turn BLE on/off during runtime
manager.use_ble_connections(False)  # or True
print("BLE enabled:", manager.get_ble_connection_status())

# Enable/disable uploads on the fly
manager.set_upload_status(False)  # keep gathering, but don't upload
print("Upload active:", manager.get_upload_status())

# Update the gathering interval at runtime (10–600 s)
manager.set_gathering_interval_seconds(45)
print("Interval (s):", manager.get_gathering_interval_seconds())
```

### Queue-Based Data Handoff (use your own processing)
Register a queue to receive each gathered snapshot (no uploads required):
```python
import queue

out_q: queue.Queue = queue.Queue()

manager = NaneosDeviceManager(
    upload_active=False,  # we'll handle data ourselves
    gathering_interval_seconds=15,
)
manager.register_output_queue(out_q)
manager.start()

try:
    while True:
        # Wait until a snapshot is ready, then pull all pending ones
        time.sleep(manager.get_seconds_until_next_upload() + 1)

        while not out_q.empty():
            snapshot = out_q.get()
            # snapshot: dict[int, pandas.DataFrame] keyed by device serial
            print(f"Received snapshot for {len(snapshot)} device(s)")
            for serial, df in snapshot.items():
                print(f"  - {serial}: {len(df)} rows")
                # >>> Your processing here (store, analyze, forward, etc.)
except KeyboardInterrupt:
    pass

manager.stop()
manager.join()
```

Make sure to modify the code according to your specific requirements. Refer to the documentation and comments within the code for detailed explanations and usage instructions.

# Logging
The package follows the usual library convention: it logs to loggers below `naneos` and prints
nothing unless the application configures logging. To see what the managers are doing:
```python
from naneos.logger import LEVEL_INFO, enable_console_logging, enable_file_logging

enable_console_logging(LEVEL_INFO)  # coloured output on stderr
enable_file_logging("logs/", LEVEL_INFO)  # appends to logs/naneos-devices.log
```
Applications that configure `logging` themselves need neither; the `naneos` logger propagates
to the root logger like any other library.

# Documentation

The documentation for the `naneos-devices` package can be found in the [package's documentation page](https://naneos-org.github.io/python-naneos-devices/).

# Protobuf
Use this command to create a py and pyi file from the proto file
```bash
protoc -I=. --python_out=. --pyi_out=. ./protoV1.proto 
```

# Testing
I recommend working with uv.
The default test run only contains tests that need no hardware:
```bash
uv run pytest
```

Tests that need a Partector connected via USB or BLE are marked `hardware` and run with:
```bash
uv run pytest -m hardware
```

Testing every supported python version:
```bash
nox -s tests
```

Lint, format and type checks (also run in CI):
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

# Building executables
Sometimes you want to build an executable for a customer with your custom script.
The build must happen on the same OS as the target OS.
For example if you want to build an executable for windows you need to build it on Windows.

```bash
pyinstaller examples/demo.py --console --noconfirm --clean --onefile
```

# Raspberry Pi as an always-on uploader
Flash Raspberry Pi OS (Bookworm or newer) with the official [Raspberry Pi Imager](https://www.raspberrypi.com/software/),
headless or with a display, and run the installer on the Pi:

```bash
curl -fsSL https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install.sh | sudo bash
```

It creates a virtual environment in `~/naneos-uploader`, installs the package from the `master`
branch, and sets up the `naneos_uploader` systemd service that starts on every boot. The service
runs the `naneos-uploader` command, which gathers from every Partector on USB and BLE and uploads
every 30 s. Re-running the installer upgrades the installation.

To install a specific branch or tag, for example a release or the hardware test branch:
```bash
curl -fsSL https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install.sh | sudo bash -s -- --ref v1.2.0
curl -fsSL https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install.sh | sudo bash -s -- --ref release_test
```

Useful afterwards:
```bash
journalctl -u naneos_uploader.service -f          # live log
sudo systemctl status naneos_uploader.service
sudo systemctl stop naneos_uploader.service
~/naneos-uploader/.venv/bin/naneos-uploader --no-upload --interval 10   # run by hand, no upload
```

# Examples
The `examples/` folder contains runnable scripts: `demo.py` (device manager with queue hand-off),
`serial_device.py` (connect to one USB device), `send_commands.py` and `download_iotweb.py`.
The script the Raspberry Pi service runs is `installers/rp-naneos-uploader/uploader-script.py`.

# Ideas for future development
* P2 bidirectional BLE implementation that allows to send commands to the P2
* Automatically activate Bluetooth or ask when BLE is used

# Contributing

## Hardware testing before a merge
Changes that touch the serial or BLE code are tested on real devices before they reach `master`:

1. Point the `release_test` branch at the feature branch: `git branch -f release_test <feature> && git push -f origin release_test`.
2. Raspberry Pi: `curl -fsSL .../installers/install.sh | sudo bash -s -- --ref release_test` (see above), then watch `journalctl -u naneos_uploader.service -f`.
3. Windows / macOS: in any virtual environment
   `pip install "https://github.com/naneos-org/python-naneos-devices/archive/release_test.tar.gz"`
   and run `pytest -m hardware` from a checkout with the devices attached.
4. When it works, open the pull request from the feature branch to `master`, merge, tag the release.

Contributions are welcome! If you encounter any issues or have suggestions for improvements, please submit an issue on the [issue tracker](https://github.com/naneos-org/python-naneos-devices/issues).

Please make sure to adhere to the coding style and conventions used in the repository and provide appropriate tests and documentation for your changes.

# License

This repository is licensed under the [MIT License](LICENSE.txt).

# Contact

For any questions, suggestions, or collaborations, please feel free to contact the project maintainer:

- Mario Huegi
- Contact: [mario.huegi@naneos.ch](mailto:mario.huegi@naneos.ch)
- [Github](https://github.com/huegi)

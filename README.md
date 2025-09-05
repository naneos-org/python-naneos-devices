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

You can install the `naneos-devices` package using pip. Make sure you have Python 3.10 or higher installed. Open a terminal and run the following command:

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
    gathering_interval_seconds=30 # clamped to [10, 600]
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
manager.use_serial_connections(True)   # or False
print("Serial enabled:", manager.get_serial_connection_status())

# Turn BLE on/off during runtime
manager.use_ble_connections(False)     # or True
print("BLE enabled:", manager.get_ble_connection_status())

# Enable/disable uploads on the fly
manager.set_upload_status(False)       # keep gathering, but don't upload
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
    upload_active=False,              # we'll handle data ourselves
    gathering_interval_seconds=15
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

# Documentation

The documentation for the `naneos-devices` package can be found in the [package's documentation page](https://naneos-org.github.io/python-naneos-devices/).

# Protobuf
Use this command to create a py and pyi file from the proto file
```bash
protoc -I=. --python_out=. --pyi_out=. ./protoV1.proto 
```

# Testing
I recommend working with uv.
Testing with the local python venv in vscode GUI or with:
```bash
uv run --env-file .env pytest
```

Testing every supported python version:
```bash
nox -s tests
```

# Building executables
Sometimes you want to build an executable for a customer with you custom script.
The build must happen on the same OS as the target OS.
For example if you want to build an executable for windows you need to build it on Windows.

```bash
pyinstaller demo/p1UploadTool.py  --console --noconfirm --clean --onefile
```

# Ideas for future development
* P2 BLE implementation that integrates into the implementation of the serial P2
* P2 Bidirectional Implementation that allows to send commands to the P2
* Automatically activate Bluetooth or ask when BLE is used

# Contributing

Contributions are welcome! If you encounter any issues or have suggestions for improvements, please submit an issue on the [issue tracker](https://github.com/naneos-org/python-naneos-devices/issues).

Please make sure to adhere to the coding style and conventions used in the repository and provide appropriate tests and documentation for your changes.

# License

This repository is licensed under the [MIT License](LICENSE.txt).

# Contact

For any questions, suggestions, or collaborations, please feel free to contact the project maintainer:

- Mario Huegi
- Contact: [mario.huegi@naneos.ch](mailto:mario.huegi@naneos.ch)
- [Github](https://github.com/huegi)

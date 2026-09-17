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

Python package for the [naneos particle solutions](https://naneos.ch) measurement devices (Partector 1, Partector 2, Partector 2 Pro). It connects to the devices over USB and Bluetooth Low Energy, delivers the measurements as pandas DataFrames, and can upload them to the naneos IoT service.

# Installation

You can install the `naneos-devices` package using pip. Python 3.11 to 3.14 is supported. Open a terminal and run the following command:

```bash
pip install naneos-devices
```
Reading your data back from the naneos IoT service (`naneos.cloud.download`) needs the InfluxDB
client, which is an optional extra: `pip install "naneos-devices[download]"`.

# Usage

## Naneos Device Manager
NaneosDeviceManager is a tiny, fire-and-forget thread that auto-manages Naneos devices over Serial and BLE, periodically gathers data, and (optionally) uploads it.
You can enable/disable transports at construction time and at runtime, adjust the gathering interval, and/or pipe data into your own code via a user-provided queue.Queue.
Clean start/stop APIs make integration trivial.

**Highlights**
- ✅ Easy on/off switches for Serial and BLE (before or during runtime)
- 🔗 BLE is connection-only: data comes from linked devices, advertisements are used for discovery only
- 🎯 Optional BLE allow-list (`ble_serial_numbers`) and link cap (`ble_max_links`, default 7)
- ⏱️ Configurable gathering interval (clamped to 10–600 s)
- 📤 Optional auto-upload (enable/disable anytime)
- 📦 Queue hand-off: receive dict[int, pandas.DataFrame] snapshots and process them in your app
- 🧵 Daemon thread with graceful shutdown

### Quick Start (fire and forget upload from all devices in reach to naneos IoT service)
```python
import time

from naneos import NaneosDeviceManager, enable_console_logging
from naneos.logger import LEVEL_INFO

enable_console_logging(LEVEL_INFO)  # the library is silent by default, see Logging

manager = NaneosDeviceManager(
    use_serial=True,
    use_ble=True,
    upload_active=True,
    gathering_interval_seconds=30,  # clamped to [10, 600]
    ble_serial_numbers=None,  # or e.g. [8617, 8764] to link only to your own devices
    ble_max_links=7,  # BlueZ handles about seven links reliably
)
manager.start()

try:
    while True:
        remaining = manager.seconds_until_next_snapshot
        print(f"Next snapshot in: {remaining:.0f}s")
        time.sleep(remaining + 1)

        for device in manager.get_devices():
            print(f"SN{device.serial_number}: {device.device_type}, {device.connection_type}")
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
manager.use_serial = True  # or False
print("Serial enabled:", manager.use_serial)

# Turn BLE on/off during runtime
manager.use_ble = False  # or True
print("BLE enabled:", manager.use_ble)

# Enable/disable uploads on the fly
manager.upload_active = False  # keep gathering, but don't upload
print("Upload active:", manager.upload_active)

# Update the gathering interval at runtime (10–600 s)
manager.gathering_interval_seconds = 45
print("Interval (s):", manager.gathering_interval_seconds)
```

### Queue-Based Data Handoff (use your own processing)
Register a queue to receive each gathered snapshot (no uploads required):
```python
import queue
import time

from naneos import NaneosDeviceManager

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
        time.sleep(manager.seconds_until_next_snapshot + 1)

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

### Talking to a device (commands and data rate)
Every connected device is available as a `PartectorDevice` handle. The API is the same
whether the device is reached over USB or BLE; a device reachable both ways is handed out
with its USB connection.
```python
import time

from naneos import NaneosDeviceManager, NotSupportedError

manager = NaneosDeviceManager(upload_active=False)
manager.start()
time.sleep(15)  # give the manager time to find and connect the devices

for device in manager.get_devices():
    print(device.serial_number, device.device_type, device.connection_type, device.is_connected)

    print(device.query("f?"))  # command with an answer -> ["422"]
    device.write("A0002!")  # command without an answer

    try:
        device.set_sample_rate(10)  # 0 (off), 1, 10 or 100 Hz
    except NotSupportedError:
        pass  # over BLE the rate is fixed at 1 Hz; it can only be changed over USB

# or address a device by its serial number
manager.query(8617, "name?")
manager.set_sample_rate(8617, 100)
```
- `query()` raises `TimeoutError` if no answer arrives (default: 0.25 s on USB, 2 s on BLE), and
  both raise `ConnectionError` if the device is gone. One command is in flight per device;
  calls from several threads queue up.
- Over BLE a command is limited to 20 bytes.
- The output queue receives the data at the rate you set. **The upload to naneos is always
  limited to 1 Hz**: samples of the same second are averaged (status bits are OR-ed).
- 100 Hz is meant for tests, not for productive use.
- A P2 Pro on USB starts in size distribution mode, where it paces itself (one line about every
  6 s). `Partector2Pro.set_size_distribution(False, sample_rate_hz=10)` switches it to the plain
  P2 line at a selectable rate.

Make sure to modify the code according to your specific requirements. Refer to the documentation and comments within the code for detailed explanations and usage instructions.

# Migrating from 1.x to 2.0
2.0 gives USB and BLE devices one API (see "Talking to a device") and removes what 1.x only
kept for compatibility. The snapshot format, the upload and the `naneos-uploader` command are
unchanged.

| 1.x | 2.0 |
|---|---|
| `manager.use_serial_connections(x)` / `get_serial_connection_status()` | `manager.use_serial = x` / `manager.use_serial` |
| `manager.use_ble_connections(x)` / `get_ble_connection_status()` | `manager.use_ble = x` / `manager.use_ble` |
| `manager.set_upload_status(x)` / `get_upload_status()` | `manager.upload_active = x` / `manager.upload_active` |
| `manager.set_gathering_interval_seconds(n)` / `get_...()` | `manager.gathering_interval_seconds = n` / `manager.gathering_interval_seconds` |
| `manager.get_seconds_until_next_upload()` | `manager.seconds_until_next_snapshot` |
| `manager.get_pending_upload_count()` | `manager.pending_upload_count` |
| `manager.get_connected_serial_devices()`, `get_connected_ble_devices()` (strings) | `manager.get_devices()` (device handles) |
| `manager.upload_blocked_devices` | removed (internal) |
| `NaneosUploadThread.upload(data)` | `naneos.upload_snapshot(data)` |
| `from naneos.iotweb import download_from_iotweb` | `from naneos.cloud.download import download_from_iotweb`, with the `download` extra |
| `device.write_line(cmd, n)` | `device.query(cmd)` (answer fields only, no timestamp) or `device.write(cmd)` |
| `Partector2(verb_freq=2)`, `set_verbose_freq(2)` (mode codes) | `Partector2(sample_rate_hz=10)`, `set_sample_rate(10)` (Hz) |
| `Partector2Pro(verb_freq=6)` | `Partector2Pro(size_distribution=True)` (default), `set_size_distribution()` |
| `device.close(blocking, shutdown, verbose_reset)` | `device.close(reset_device=True)`, `device.power_off()` |
| `device.clear_data_cache()` | removed; `get_data()` returns everything received |
| `naneos.partector.scanPartector`, `scan_for_serial_partectors()` | `naneos.usb.partector.scan.scan_serial_ports()` |
| `naneos.serial_utils.list_serial_ports` | `naneos.usb.partector.scan.list_serial_ports` |
| `NaneosDeviceDataPoint.DEV_TYPE_*` / `CONN_TYPE_*`, its DataFrame static methods | `naneos.DeviceType` / `naneos.ConnectionType`, `naneos.frames` |
| `PartectorBluePrint` | `naneos.usb.partector.device.UsbPartector` |

The modules were regrouped by transport, with one subpackage per device family (today: `partector`). `from naneos import ...` is unchanged; deep imports move:

| 1.x module | 2.0 module |
|---|---|
| `naneos.partector.partector1` / `partector2` / `partector2_pro` | `naneos.usb.partector.device` |
| `naneos.partector.partector_serial_manager`, `naneos.partector` | `naneos.usb.partector.manager`, `naneos.usb` |
| `naneos.partector.scan` | `naneos.usb.partector.scan` |
| `naneos.partector.blueprints._data_structure` | `naneos.usb.partector.layouts` |
| `naneos.partector_ble.partector_ble_manager`, `naneos.partector_ble` | `naneos.ble.partector.manager`, `naneos.ble` |
| `naneos.partector_ble.partector_ble_connection` / `..._scanner` | `naneos.ble.partector.connection` / `naneos.ble.partector.scanner` |
| `naneos.partector_ble.decoders` / `partector_ble_decoder` | `naneos.ble.partector.characteristics` / `naneos.ble.partector.advertisement` |
| `naneos.manager.naneos_device_manager` | `naneos.manager` |
| `naneos.iotweb` | `naneos.cloud` (`upload`, `download`) |
| `naneos.protobuf` | unchanged |
| (new) | `naneos.usb.transport`: the serial transport shared by every USB device family |
| `naneos.uploader` (the `naneos-uploader` command) | `naneos.cli` |
| `naneos.logger` | unchanged |

A serial device no longer reconnects on its own: when `is_connected` turns False, close it and
create a new one (the managers do this for you). Its constructor raises `ConnectionError`
instead of returning an unconnected object.

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
The upload format is defined in `src/naneos/protobuf/protoV1.proto` (shared with the backend, never
renumber fields). Regenerate the Python module and the stub in that directory with:
```bash
protoc -I=. --python_out=. --pyi_out=. ./protoV1.proto
```

# Testing
I recommend working with uv.
The default test run only contains tests that need no hardware:
```bash
uv run pytest
```

Tests that need a Partector connected via USB or BLE are marked `hardware`, tests that need
internet access and an IoT token are marked `network`:
```bash
uv run pytest -m hardware
IOT_GUEST_TOKEN=... uv run pytest -m network
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
~/naneos-uploader/.venv/bin/naneos-uploader --ble-allow 8617,8764 --ble-max-links 2
```

BLE on the Pi is connection-only and scans passively: the installer starts `bluetoothd` with
`--experimental`, which BlueZ needs for passive scanning, so the shared WiFi/BLE antenna is not
loaded with scan requests. The log line `BLE scanning (passive).` confirms it; `(active)` plus a
warning means BlueZ refused and the uploader fell back to active scanning.

# Examples
The `examples/` folder contains runnable scripts: `demo.py` (device manager with queue hand-off),
`serial_device.py` (connect to one USB device), `send_commands.py` (send a command file to a device on
USB or BLE) and `download_iotweb.py`.
The Raspberry Pi service runs the `naneos-uploader` command, implemented in `src/naneos/cli.py`.

# Ideas for future development
* Automatically activate Bluetooth or ask when BLE is used

# Contributing

## Hardware testing before a merge
Changes that touch the serial or BLE code are tested on real devices before they reach `master`:

1. Point the `release_test` branch at the feature branch: `git branch -f release_test <feature> && git push -f origin release_test`.
2. Raspberry Pi: `curl -fsSL .../installers/install.sh | sudo bash -s -- --ref release_test` (see above), then watch `journalctl -u naneos_uploader.service -f`.
3. Windows / macOS: in any virtual environment
   `pip install "https://github.com/naneos-org/python-naneos-devices/archive/release_test.tar.gz"`
   and run `pytest -m hardware` from a checkout with the devices attached. To switch an existing
   environment to another branch with the same version number, add `--force-reinstall --no-deps`;
   pip otherwise keeps what is installed.
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

# naneos-devices


[![GitHub Issues][gh-issues]](https://github.com/naneos-org/python-naneos-devices/issues)
[![GitHub Pull Requests][gh-pull-requests]](https://github.com/naneos-org/python-naneos-devices/pulls)
[![Ruff][ruff-badge]](https://github.com/astral-sh/ruff)
[![License][mit-license]](https://github.com/naneos-org/python-naneos-devices/blob/master/LICENSE.txt)

<!-- hyperlinks -->
[gh-issues]: https://img.shields.io/github/issues/naneos-org/python-naneos-devices
[gh-pull-requests]: https://img.shields.io/github/issues-pr/naneos-org/python-naneos-devices
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
[mit-license]: https://img.shields.io/badge/license-MIT-blue.svg
<!-- hyperlinks -->

[![Projektlogo](https://raw.githubusercontent.com/naneos-org/public-data/master/img/logo_naneos.png)](https://naneos.ch)

Python package for the [naneos particle solutions](https://naneos.ch) measurement devices (Partector 1, Partector 2, Partector 2 Pro). It connects to the devices over USB and Bluetooth Low Energy, delivers the measurements as pandas DataFrames, and can upload them to the naneos IoT service.

# Installation

Python 3.11 to 3.14 is supported.

```bash
pip install naneos-devices
```

# The device manager

`NaneosDeviceManager` is all most applications need. It runs as a background thread, finds and
connects every Partector on USB and Bluetooth, gathers their data in snapshots and, if you
want, uploads them to the naneos IoT service.

- 🔌 USB and BLE, each can be switched on and off, also while running
- 🎯 Optional BLE allow-list (`ble_serial_numbers`) and link limit (`ble_max_links`, default 7)
- ⏱️ Gathering interval of 10 to 600 s
- 📤 Optional upload to the naneos IoT service (always at 1 Hz)
- 📦 Snapshots as `dict[int, pandas.DataFrame]` on a queue, for your own processing
- ⚡ Live data: every data point on a queue the moment it arrives
- 💬 Send commands to a device, read its answers and set its data rate, the same way on USB and BLE

## Quick start: upload everything in reach
Example: [`examples/quick_start.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/quick_start.py)
```python
import time

from naneos import NaneosDeviceManager, enable_console_logging
from naneos.logger import LEVEL_INFO

enable_console_logging(LEVEL_INFO)  # the library is silent by default

manager = NaneosDeviceManager(
    use_serial=True,
    use_ble=True,
    upload_active=True,
    gathering_interval_seconds=30,  # clamped to [10, 600]
    ble_serial_numbers=None,  # or e.g. [8617, 8764] to link only to your own devices
)
manager.start()

try:
    while True:
        time.sleep(manager.seconds_until_next_snapshot + 1)
        for device in manager.get_devices():
            print(device)  # e.g. <Partector2 SN8617 P2 serial>
except KeyboardInterrupt:
    pass

manager.stop()
manager.join()
```

## Process the data yourself
Example: [`examples/queue_handoff.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/queue_handoff.py)

Register a queue and every snapshot is put on it, with or without the upload:
```python
import queue
import time

from naneos import NaneosDeviceManager

snapshots: queue.Queue = queue.Queue()

manager = NaneosDeviceManager(upload_active=False, gathering_interval_seconds=15)
manager.register_output_queue(snapshots)
manager.start()

try:
    while True:
        time.sleep(manager.seconds_until_next_snapshot + 1)
        while not snapshots.empty():
            snapshot = snapshots.get()  # dict[int, pandas.DataFrame], keyed by serial number
            for serial_number, df in snapshot.items():
                print(f"SN{serial_number}: {len(df)} rows, mean LDSA {df['ldsa'].mean():.1f}")
except KeyboardInterrupt:
    pass

manager.stop()
manager.join()
```
The frames are indexed by the unix timestamp in milliseconds; the columns are the fields of
[`NaneosDeviceDataPoint`](https://naneos-org.github.io/python-naneos-devices/reference/naneos/data_point/) (`ldsa`, `particle_number_concentration`,
`average_particle_diameter`, `device_status`, ...).

## Live data
Example: [`examples/live_data.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/live_data.py)

Snapshots arrive every 10 s at best. For a live view, register a live queue: it receives every
data point the moment it arrives, as a `NaneosDeviceDataPoint`, next to the snapshots and the upload.
```python
import queue

from naneos import NaneosDeviceManager

live: queue.Queue = queue.Queue(maxsize=10_000)  # bounded: a full queue drops its oldest point

manager = NaneosDeviceManager(upload_active=False)
manager.register_live_queue(live)
manager.start()

while True:
    point = live.get()
    print(point.serial_number, point.connection_type, point.unix_timestamp, point.ldsa)
```
[`examples/live_plot.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/live_plot.py) uses this to plot the diffusion current of a device on USB.

The points come at the rate of the device (1 Hz, or what you set over USB). A device that is
connected over USB and BLE delivers its USB points only.

## Change it while it runs
Example: [`examples/runtime_controls.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/runtime_controls.py)
```python
manager.use_serial = False  # USB devices off / on
manager.use_ble = True  # BLE devices off / on
manager.upload_active = False  # keep gathering, stop uploading
manager.gathering_interval_seconds = 45  # 10 to 600 s

print(manager.seconds_until_next_snapshot, manager.pending_upload_count)
```

## Talk to a device: commands and data rate
Example: [`examples/device_commands.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/device_commands.py)

Every connected device is available as a handle with the same API over USB and BLE. A device
that is reachable both ways is handed out with its USB connection.
```python
from naneos import NotSupportedError

for device in manager.get_devices():
    print(device.serial_number, device.device_type, device.connection_type)

    print(device.query("f?"))  # a command with an answer -> ["422"]
    device.write("A0002!")  # a command without an answer

    try:
        device.set_sample_rate(10)  # 0 (off), 1, 10 or 100 Hz
    except NotSupportedError:
        pass  # over BLE the rate is fixed at 1 Hz, it can only be changed over USB

# or address a device by its serial number
manager.query(8617, "name?")
manager.write(8617, "A0002!")
manager.set_sample_rate(8617, 100)
```
- An unknown serial number raises `KeyError`, a lost device `ConnectionError`, a missing answer
  `TimeoutError`. Calls are safe from any thread.
- Your queue receives the data at the rate you set. **The upload to naneos is always limited to
  1 Hz.** 100 Hz is meant for tests.
- The rate is not remembered: a device that reconnects starts at 1 Hz again.
- A Partector 2 Pro on USB starts in size distribution mode, where it sets its own pace. See the
  [documentation](https://naneos-org.github.io/python-naneos-devices/user-guide/devices/) for its modes and the other details.

# Logging
The library logs to loggers below `naneos` and prints nothing by default:
```python
from naneos.logger import LEVEL_INFO, enable_console_logging, enable_file_logging

enable_console_logging(LEVEL_INFO)  # coloured output on stderr
enable_file_logging("logs/", LEVEL_INFO)  # appends to logs/naneos-devices.log
```

# More examples
| Example | What it shows |
|---|---|
| [`quick_start.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/quick_start.py) | upload everything in reach |
| [`queue_handoff.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/queue_handoff.py) | process the snapshots yourself |
| [`live_data.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/live_data.py) | every data point the moment it arrives |
| [`live_plot.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/live_plot.py) | live plot of the diffusion current of a device on USB (needs `pip install matplotlib`) |
| [`runtime_controls.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/runtime_controls.py) | switch transports, upload and interval while running |
| [`device_commands.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/device_commands.py) | commands, answers and the data rate |
| [`send_commands.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/send_commands.py) | send a file of commands to one device |
| [`serial_device.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/serial_device.py) | one USB device without the manager |
| [`download_iotweb.py`](https://github.com/naneos-org/python-naneos-devices/blob/master/examples/download_iotweb.py) | read your data back from the naneos IoT service (needs `pip install "naneos-devices[download]"`) |

# Documentation
The [documentation](https://naneos-org.github.io/python-naneos-devices/) covers the rest:

- [Raspberry Pi as an always-on uploader](https://naneos-org.github.io/python-naneos-devices/user-guide/raspberry-pi-setup/)
- [Devices, commands and the Partector 2 Pro modes](https://naneos-org.github.io/python-naneos-devices/user-guide/devices/)
- [Migrating from 1.x to 2.0](https://naneos-org.github.io/python-naneos-devices/user-guide/migration-2.0/)
- [Development: tests, protobuf, releases](https://naneos-org.github.io/python-naneos-devices/development/contributing/)
- API reference

# License
This repository is licensed under the [MIT License](https://github.com/naneos-org/python-naneos-devices/blob/master/LICENSE.txt).

# Contact
- Mario Huegi, [mario.huegi@naneos.ch](mailto:mario.huegi@naneos.ch), [GitHub](https://github.com/huegi)
- Issues and suggestions: [issue tracker](https://github.com/naneos-org/python-naneos-devices/issues)

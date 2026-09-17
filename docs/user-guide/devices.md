# Devices and commands

The README shows the short version. This page has the details.

## Device handles

`NaneosDeviceManager.get_devices()` returns one `PartectorDevice` per connected device, whatever
it is connected with. A device that is reachable over USB and BLE is handed out with its USB
connection: USB is faster and the only way to change the data rate.

| | USB | BLE |
|---|---|---|
| `write(command)` / `query(command)` | yes | yes, a command is limited to 20 bytes |
| default `query()` timeout | 0.25 s | 2 s (answers take 0.25 s to 1 s) |
| `set_sample_rate(hz)` | 0, 1, 10, 100 Hz | raises `NotSupportedError`, fixed at 1 Hz |
| `firmware_version`, `device_type` | known on connect | known a moment after the connect |

One command is in flight per device; calls from several threads queue up. Answers carry no
reference to their command, so `query()` must only be used for commands that answer, and
`write()` for those that do not.

Errors: `ConnectionError` (device gone, or a BLE device without the command characteristics),
`TimeoutError` (no answer), `ValueError` (unknown rate, BLE command too long),
`NotSupportedError` (the transport or mode cannot do it), and `KeyError` from
`manager.get_device(sn)` and the `manager.write / query / set_sample_rate` shortcuts.

## Data rate and upload

The output queue receives the data at the rate that is set. The upload to the naneos IoT
service is always limited to 1 Hz: samples of the same second are averaged, status bits are
OR-ed. 100 Hz is meant for tests, not for productive use.

The rate belongs to the connection: when a device is unplugged or reconnects, the manager
creates a new connection at 1 Hz and `set_sample_rate()` has to be called again.

## Partector 2 Pro modes (USB)

A P2 Pro on USB starts in **size distribution mode**: one line with the size distribution about
every 6 s, paced by the device. `sample_rate_hz` is `None` and `set_sample_rate()` raises
`NotSupportedError`. To get the plain P2 line at a selectable rate, switch the mode on the handle:

```python
pro = manager.get_device(8764)  # a naneos.usb.partector.Partector2Pro
pro.set_size_distribution(False, sample_rate_hz=10)
pro.set_sample_rate(100)
pro.set_size_distribution(True)  # back to the size distribution
```

With the gain test active (the default), every mode switch holds the data of the device back
for at least 10 s while it settles.

## Gain test and pulse diagnostics (USB)

P2 and P2 Pro on USB run the electrometer gain test and report the pulse diagnostics by default.
Both can be switched off: `NaneosDeviceManager(serial_gain_test=False,
serial_pulse_diagnostics=False)`. The gain test holds the data of a device back for at least
10 s after every connect.

## Without the manager

`naneos.usb.partector` has the device classes (`Partector1`, `Partector2`, `Partector2Pro`) and
`PartectorSerialManager`; `naneos.ble.partector` has `PartectorBleManager`. See
`examples/serial_device.py` and the API reference. A USB device does not reconnect on its own:
when `is_connected` turns False, close it and create a new one (the managers do this for you).

## Reading data back from the naneos IoT service

`naneos.cloud.download.download_from_iotweb()` needs the InfluxDB client, an optional extra:
`pip install "naneos-devices[download]"`. See `examples/download_iotweb.py`.

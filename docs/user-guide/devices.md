# Devices and commands

The README shows the short version. This page has the details.

## Device handles

`NaneosDeviceManager.get_devices()` returns one `PartectorDevice` per connected device, whatever
it is connected with. A device that is reachable over USB and BLE is handed out with its USB
connection: USB is faster and the only way to change the data rate.

| | USB | BLE |
|---|---|---|
| `write(command)` / `query(command)` | yes | yes, a command is limited to 20 bytes |
| default `query()` timeout | 1 s | 2 s (answers take 0.25 s to 1 s) |
| `set_sample_rate(hz)` | 0, 1, 10, 100 Hz or `None` (the default of the device) | raises `NotSupportedError`, fixed at 1 Hz (`None` is accepted) |
| `firmware_version`, `device_type` | known on connect | known a moment after the connect |
| `read_ui_curve()` / `read_pulse_form()` | 10 s sweep + about 1 s | 10 s sweep + about 40 s / about 50 s |

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

`manager.sample_rate_hz` (also a constructor argument) sets the rate of every USB device at
once: `None` (the default) leaves each device at its own default, 1, 10 or 100 Hz applies to
all connected devices within a second and to every device that connects later. A rate set on a
single handle with `set_sample_rate()` is not remembered: a device that reconnects gets the
manager setting.

## Snapshots and live data

| | Snapshots (`register_output_queue`) | Live data (`register_live_queue`) |
|---|---|---|
| Item | `dict[int, pandas.DataFrame]`, one frame per device | one `NaneosDeviceDataPoint` |
| When | every gathering interval (10 to 600 s) | the moment the point arrives (about 1 ms after it was read) |
| USB and BLE at once | USB rows only | USB points only |
| Cleaning | sorted, duplicate timestamps removed | none, points as received |
| Used for the upload | yes | no |

Both can be registered at the same time. The live points are pushed from the threads that
receive them (the serial reader threads and the BLE event loop), so the manager never blocks on
the live queue: give it a `maxsize`, and when it is full the oldest point is dropped to make
room. `manager.live_points_dropped` counts them. An unbounded queue that nobody reads grows
without limit, at 100 Hz by about 200 kB per second and device.

A P2 Pro in size distribution mode delivers one point per inversion cycle (6–21 s, depending
on its integration time), also on the live queue.

## Partector 2 Pro modes (USB)

A P2 Pro on USB starts in **size distribution mode**: one line with the size distribution per
inversion cycle (6–21 s, depending on the integration time), paced by the device, and
`sample_rate_hz` is `None`. A rate switches it to the plain P2 line, `None` switches it back:

```python
pro = manager.get_device(8764)
pro.set_sample_rate(10)  # the plain P2 line at 10 Hz, no size distribution
pro.set_sample_rate(100)
pro.set_sample_rate(None)  # back to the size distribution
```

`manager.sample_rate_hz = 10` does the same for every USB device, P2 and P2 Pro alike.

With the gain test active (the default), every mode switch holds the data of the device back
for at least 10 s while it settles.

## Gain test and pulse diagnostics (USB)

P2 and P2 Pro on USB run the electrometer gain test and report the pulse diagnostics by default.
Both can be switched off: `NaneosDeviceManager(serial_gain_test=False,
serial_pulse_diagnostics=False)`. The gain test holds the data of a device back for at least
10 s after every connect.

## UI curve and pulse form

A P2 or P2 Pro with firmware 418 or newer has two diagnostics that are read on request, over
USB and BLE alike:

- `read_ui_curve()` makes the device sweep its corona voltage and returns a `UiCurve`: the
  electrometer current (nA) over the corona voltage (V), 100 points sorted by voltage. The
  sweep takes 10 s and disturbs the measurement, so the data points of the device are held back
  until it has settled: about 15 s over USB (the integration time is known there), about 30 s
  over BLE.
- `read_pulse_form()` returns a `PulseForm`: the electrometer current (nA) along one charging
  pulse, 200 samples in time order. The measurement goes on undisturbed.

Both block: over USB the answer comes within a second of the sweep, over BLE the device sends
one packet every 2 s, so a UI curve takes about 40 s and a pulse form about 50 s after the
command. Errors: `NotSupportedError` (a P1, or firmware older than 418), `TimeoutError` (the
readout stayed incomplete, default 30 s over USB and 90 s over BLE), `ConnectionError`.

```python
curve = manager.read_ui_curve(8617)  # or device.read_ui_curve()
print(curve.voltages[-1], curve.currents[-1])  # 3735 V, 1.98 nA
form = manager.read_pulse_form(8617)
print(max(form.currents))
```

**On a schedule.** By default the manager reads both of every connected device once an hour,
at the full hour (`diagnostics_interval_hours=1`, also a property; `None` switches it off,
`request_diagnostics()` reads now). The devices are read one after the other on a thread of
the manager, so with several BLE devices a round takes a few minutes. Each result is uploaded
to the naneos IoT service when the upload is active (`/uicurve` and `/pulseform`, retried
like the snapshots) and put on the queue given to `register_diagnostics_queue()`, if any.
The interval is 0.5 to 24 hours; anything else raises a `ValueError`. The uploader service has
the same setting: `naneos-uploader --diagnostics-interval 6`, `0` for never.

## Without the manager

`naneos.usb.partector` has the device classes (`Partector1`, `Partector2`, `Partector2Pro`) and
`PartectorSerialManager`; `naneos.ble.partector` has `PartectorBleManager`. See
`examples/serial_device.py` and the API reference. A USB device does not reconnect on its own:
when `is_connected` turns False, close it and create a new one (the managers do this for you).

## Reading data back from the naneos IoT service

`naneos.cloud.download.download_from_iotweb()` needs the InfluxDB client, an optional extra:
`pip install "naneos-devices[download]"`. See `examples/download_iotweb.py`.

# Migrating from 1.x to 2.0
2.0 gives USB and BLE devices one API (see [Devices and commands](devices.md)) and removes what 1.x only
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
| `naneos.protobuf` (`protoV1_pb2`) | `naneos.protobuf` with `proto_v2_pb2`; the upload uses the v2 endpoint `.../proto/v2/combined_data` |
| (new) | `naneos.usb.transport`: the serial transport shared by every USB device family |
| `naneos.uploader` (the `naneos-uploader` command) | `naneos.cli` |
| `naneos.logger` | unchanged |

A serial device no longer reconnects on its own: when `is_connected` turns False, close it and
create a new one (the managers do this for you). Its constructor raises `ConnectionError`
instead of returning an unconnected object.


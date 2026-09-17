# Refactoring & cleanup overview

Snapshot of the codebase as of 2026-09-11 (branch `dev_improve_raspi_ble`, started at v1.1.17, released as v1.2.0).
Goal: simplify the repo and fix known bugs **before** new features are built.

Legend: `[ ]` open, `[x]` done. Priorities: **P0** bug / data loss, **P1** requested cleanup,
**P2** structural simplification, **P3** hygiene.

---

## 0. Snapshot

| Metric | Value |
|---|---|
| Source lines (`src/`, without generated `_pb2`) | ~4 900 at the start; Python 3.11-3.14, bleak 3, pandas 3, protobuf 7 since 1.2.0 |
| Largest files | `partector_ble_connection.py` 731, `_data_structure.py` 565, `_partector_blueprint.py` 541, `partector_ble_manager.py` 415 |
| `ruff check` | clean with `E, F, I, B, UP` |
| `ruff format --check` | clean (`[tool.ruff]` with line length 100 in `pyproject.toml`) |
| `mypy src` | clean |
| Tests runnable without hardware | 53; the 9 hardware and 2 network tests are marked and skipped by default |
| `__main__` demo blocks inside library modules | none, runnable scripts live in `examples/` |
| CI | `ci.yml`: ruff, mypy, pytest on 3.10-3.13 (hardware tests excluded via marker) |

---

## 1. P0 - Bugs found while reading (fix first)

- [x] **Module-level data-structure dicts are mutated in place.**
  `partector2.py` and `partector2_pro.py` do `self._data_structure = PARTECTOR2_DATA_STRUCTURE_V320`
  and then `self._data_structure.update(...)` for pulse-diagnostic / gain-test columns. The
  module constant is changed for the whole process, so the next device (or the same device with
  `gain_test_active=False`) expects the wrong line length and drops every data line as "info".
  Fix: copy (`dict(...)`) before extending, or build the structure per instance.

- [x] **`_fw` / `_integration_time` are not initialised.** `_init_get_device_info()` swallows every
  exception, but `Partector2._init_serial_data_structure()` and `_create_naneos_device_point()`
  read `self._fw` unconditionally -> `AttributeError` on a flaky device during construction,
  after the reader thread has already been started. Initialise both in `_init_variables()`.

- [x] **`__scan_port` can raise `UnboundLocalError`.** In `scanPartector.py` the `except` branch
  references `partector`, which does not exist if `ScanPartector(port=port)` itself raised.

- [x] **`" usb_cc_voltage"` typo in `protobuf.py` (leading space).** The field is never uploaded.

- [x] **Serial-manager data is read from two threads without a lock.**
  `PartectorSerialManager._manager_loop()` calls `_fetch_data()` every second, and
  `NaneosDeviceManager` calls `get_data()` (which also calls `_fetch_data()` and then swaps
  `self._data`) from its own thread. `PartectorBluePrint.get_data()` is therefore also called
  concurrently on the same device (`list(self._queue)[0:-1]` + `clear_data_cache()`), so points
  can be duplicated or lost. Decide on one owner of the data (the manager loop) and hand it over
  through a `queue.Queue` or under a lock.

- [x] **P2 Pro serial columns `surface` and `steps` are silently dropped.** The serial data
  structures use keys `surface`, `steps`, `flow_from_phase_angle`, `DAC`, `HVon`, `idiffset`,
  `lag` which are not fields of `NaneosDeviceDataPoint`; `setattr` adds them as stray attributes
  and `to_dict()` ignores them. The dataclass fields are `particle_surface` / `steps_inversion`,
  which the uploader would send if they existed. Rename the keys or drop them explicitly.

- [x] **Upload failure = data loss.** (fixed: the manager keeps the last `MAX_PENDING_UPLOADS` snapshots and retries them oldest first; 4xx responses are dropped, network errors and 5xx retried) `NaneosDeviceManager._loop()` clears `self._data` before the
  upload and nothing is retried on a non-200 / exception (the callback comment even says
  "delete data because it was corrupted"). On a Raspberry Pi with flaky WiFi this is the main
  way data disappears. Decide: keep a bounded retry buffer (e.g. last N snapshots) or document
  the limitation.

- [x] **`Partector2ProCs.set_catalyst_state()` writes `self._cs_state` but everything else reads
  `self._catalyst_state`.** Goes away with the CS removal (section 2), listed for completeness.

- [x] **mypy errors** (4): Optional serial number used as dict key in `partector_ble_manager.py`;
  `Index.round` in `naneos_upload_thread.py`. Cheap to fix, and then mypy can go into CI.

---

## 2. P1 - Remove the catalytic stripper (`*_cs`) entity

Everything that exists only for the P2 Pro CS:

- [x] Delete `src/naneos/partector/partector2_pro_cs.py` (whole file, incl. its `__main__` demo).
- [x] `_data_structure.py`
  - [x] delete `PARTECTOR2_PRO_CS_DATA_STRUCTURE_V315`
  - [x] delete `NaneosDeviceDataPoint.cs_status` field and the `"cs_status": "Int32"` dtype entry
  - [x] delete `DEV_TYPE_P2PRO_CS = 3` and fix the comment on `device_type`
    (`# 0: P2, 1: P1, 2: P2PRO, 3: P2PRO_CS`). **Do not reuse the number 3**; the backend still
    knows it.
- [x] `scanPartector.py`
  - [x] drop `q_2_pro_cs` from `scan_for_serial_partector`, `scan_for_serial_partectors`, `__scan_port`
  - [x] drop the `"P2proCS"` branches and the `"P2proCS"` key of the returned dict
    (callers: `partector_serial_manager.py` uses P1/P2/P2pro keys, `send_commands.py` merges all)
- [x] `protobuf.py`: delete the `cs_status` block (`# Needed for the garagenbox`).
- [x] `protoV1.proto`: **leave field 38 `cs_status` and the type comment as they are.** The file is
  the server's schema ("make sure to be up to date with the version from: upload timeseries");
  removing or renumbering would break wire compatibility. Optionally add `// reserved, former P2proCS`.
- [x] Remove leftovers: `tests/demo_martin.py` line in `.gitignore`, `df_garagae.pkl` comment,
  `partector_data.pkl` in the repo root (only used by the `__main__` of the upload thread).
- [x] grep afterwards: `grep -rni "_cs\b\|procs\|catalyst\|cs_status" src tests examples docs README.md`

---

## 3. P2 - Things that are too complicated

### 3.1 Serial side (`naneos/partector`)

- [x] **`PartectorSerialManager` keeps three parallel dicts** (`_connected_p1`, `_connected_p2`,
  `_connected_p2_pro`) and every method is written three times (`_fetch_data`,
  `get_connected_device_strings`, `get_connected_addresses`, `get_connected_serial_numbers`,
  `_disconnect_unplugged_ports`, `_connect_to_new_ports`, `_close_all_ports`).
  -> one `dict[str, PartectorBluePrint]` keyed by port; device type comes from the instance.
  Also remove the stray `print(f"Disconnecting P2 Pro port: ...")`.

- [x] **`scanPartector.py` has two near-identical scan functions** threading four queues through
  `__scan_port`. -> one `scan_serial_ports() -> list[FoundDevice(sn, port, kind, fw)]`, and the
  two public functions become one-line filters on top of it. Rename the file to `scan.py`
  (camelCase file name is the only one in the repo).

- [x] **`PartectorBluePrint` does too much** (done in 7.3): `Thread` + `PartectorDefaults` mixin + ABC;
  the constructor scans ports, opens serial, starts the thread, queries the device and configures
  it. Overlapping "connection check" methods: `_check_connection`, `_check_serial_connection`,
  `_check_device_connection`, `_run_check_connection`, `_checker_thread`. Suggested split:
  - a small `SerialTransport` (open/close/readline/write, reconnect) with no threads
  - a `PartectorDevice` (protocol: `N?`, `f?`, `H?`, verbose freq, data-structure selection)
  - the reader thread owned by the manager, not by every device
  Also: constants from `PartectorDefaults` become class attributes, `hw_version: str = "None"`
  becomes `Optional[str]`, `write_line()` stops smuggling its arguments through instance state
  (`custom_info_str` / `custom_info_size`), `_serial_wrapper` stops returning `False | None | value`.

- [x] **Configuration block copied three times.** The `opd01!/opd00!` + `h2001!/e1100!` +
  `_wait_with_data_output_until` sequence exists in `Partector2._init_serial_data_structure`
  and twice in `Partector2Pro._set_verbose_freq`. -> one `_apply_diagnostics_config()` in the base.
  `_set_verbose_freq` on the P2 Pro also selects the data structure and switches modes; split
  "set mode" from "set frequency".

- [x] **Six near-identical serial data-structure dicts.** `PARTECTOR2_DATA_STRUCTURE_V320`,
  `..._V295_V297_V298`, `..._LEGACY` are byte-for-byte identical; `..._V265_V275` only adds
  `lag`; the two P2 Pro dicts differ in one column. -> one base list per family plus small
  per-firmware deltas, or a single `FIRMWARE_COLUMNS` table. Keep the firmware -> structure
  selection in one function instead of in each class.

- [x] **Delete dead code**: `blueprints/_partectorCheckerThread.py` (never imported),
  `serial_utils/list_serial_ports._get_all_open_ports` (commented-out call), commented code in
  `get_data` / `_get_and_check_info`, the 100-iteration open/close loop in `_check_port_function`
  (document why, or replace with a bounded retry with sleep).

- [x] `list_serial_ports(ports_exclude: list = [])` and
  `sort_and_clean_naneos_data(serial_only: list[int | None] = [])` use mutable defaults.

- [x] `utils/send_commands.py` has no `__init__.py`, a hard-coded `/Users/huegi/Downloads/...`
  path and only filters lines starting with `"2"`. Move to `examples/` or make it a proper CLI.

### 3.2 Shared data model (`blueprints/_data_structure.py`)

Done: `naneos/data_point.py` (dataclass, `DeviceType`, `ConnectionType`) and `naneos/frames.py`
(dtype mapping, DataFrame builders, `sort_and_clean_naneos_data`). `_data_structure.py` keeps only
the serial line layouts plus compatibility re-exports; the `DEV_TYPE_*` / `CONN_TYPE_*` aliases and
the three DataFrame static methods stay on the dataclass for users of 1.1.x. Frames are indexed by
unix ms everywhere; the uploader converts to seconds unconditionally.

- [x] **`NaneosDeviceDataPoint` lives in a "private" module under `partector/blueprints/` but is the
  central type** for BLE, protobuf, manager and tests. Move it to `naneos/data_point.py` (or
  `naneos/model.py`) and re-export from `naneos/__init__.py`. The module-level helpers
  `add_to_existing_naneos_data` / `sort_and_clean_naneos_data` belong next to the manager.
- [x] The dataclass mixes 55 optional measurement fields with class constants (`DEV_TYPE_*`,
  `CONN_TYPE_*`, four `BLE_*_FIELD_NAMES` sets, `PANDAS_DTYPES_MAPPING`, `MAX_ROWS_PER_DEVICE`) and
  pandas conversion logic. -> `DeviceType` / `ConnectionType` enums, dtype mapping and
  DataFrame builders in a separate `frames.py`.
- [x] `PANDAS_DTYPES_MAPPING["connection_type"] = "Int32"` is wrong (it is a string). It only works
  because `astype(errors="ignore")` hides the failure, which also hides any real dtype problem.
- [x] `device_type` defaults to `0` (= P2), so a P2 Pro seen only by advertisement is reported as
  P2; `sort_and_clean_naneos_data` then has a special case to drop P2 rows when P2PRO rows exist.
  Make the default `None` / unknown and let the advertisement decoder not claim a type.
- [x] Timestamps: serial and BLE-connection points are in ms, the scanner truncates to whole
  seconds `* 1000`, and the uploader guesses the unit with `df.index[0] > 1e12`. Pick one unit at
  the source (ms int) and drop the heuristic.
- [x] `to_pandas_df_row` / `add_data_point_to_dict` are the slow per-point path kept "for
  compatibility"; only `__main__` demos and the serial manager still use them. Remove after 3.1.

### 3.3 BLE side (`naneos/partector_ble`)

Done in commits `e7f9f96`, `25eeeec` and the connection split. Not verified against a real
adapter: run the `hardware` BLE tests (`test_02_01` to `test_02_03`) on a Pi and a Windows box
before releasing, the Windows-only branches in the connection are untested here.

- [x] **`PartectorBleConnection._run()` is ~200 lines** of nested try/except with three separate
  places that recreate the `BleakClient`, Windows-only branches, and a hand-rolled 1 s tick.
  Extract: `_connect_once()`, `_handle_connect_error(e)`, `_recreate_client()`, `_watchdog()`
  (the std/aux timeout check). Keep the well-documented behaviour, drop the duplication.
- [x] `_decode_routine()` task is created with `create_task` and its reference dropped (asyncio
  can garbage-collect it; keep a reference and cancel it in `stop()`).
- [x] `start()` logs `"SN{self._serial_number}"` (no f-string, wrong attribute name).
- [x] `_disconnect_gracefully()` sleeps 0.5 s four times "for Windows" on every platform; gate it on
  `_SERIALIZE_CONNECTS` like the connect path already does.
- [x] **`PartectorBleManager` tracks connections in two dicts** (`_connections: {sn: (task, type)}`
  and `_connection_objects: {sn: connection}`) and rebuilds tuples to update the device type.
  -> one `dict[int, BleLink]` holding task, connection and type.
- [x] Three shutdown paths (`_kill_all_connections`, `_finish_all_connections`,
  `_finish_all_connections_blocking`) and four adapter-check methods
  (`_bleak_is_bluetooth_adapter_available`, `_linux_is_bluetooth_adapter_available`,
  `_is_bluetooth_adapter_available`, `_wait_for_bluetooth_adapter`; one with a German docstring).
  The manager loop already uses `scanner.is_discovering` as the adapter check, so the
  `bluetoothctl` probe is only needed once before start. Collapse to one `shutdown()` and one
  `adapter_available()`.
- [x] `get_connected_serial_numbers()` returns every serial with a task (including devices that are
  only being retried) while `get_connected_device_strings()` returns only live links. Align.
- [x] `pd.set_option("future.no_silent_downcasting", True)` at import time changes a global pandas
  option for the host application. Remove or scope it.
- [x] Decoders: `partectod_ble_decoder_aux_error.py` (typo in file name); every decoder is a class
  with one `decode` and ten one-line `_get_*` classmethods with docstrings. A table of
  `(field, slice, factor)` per characteristic plus one generic decode loop would replace ~450
  lines with ~80 and make the offsets reviewable at a glance.
- [x] `partector_ble/__init__.py` is empty; export `PartectorBleManager`.

### 3.4 Device manager / upload (`naneos/manager`, `naneos/iotweb`)

- [x] `NaneosDeviceManager._loop()` starts an upload thread and immediately `join()`s it, so the
  manager blocks for up to the 10 s request timeout every interval. Either call `upload()`
  directly or let the thread run and collect the result later. (calls `upload()` directly now)
- [x] `NaneosUploadThread.get_body()` builds JSON by string formatting; use `json.dumps`.
  `published_at` is naive local time; use UTC with tz info.
- [x] `naneos_device_manager.py` contains four example functions (`minimal_example`,
  `queue_example`, `test_naneos_device_manager`, `ble_connect_example`, one of them sending
  SIGINT to the own process). Move to `examples/`, they duplicate `examples/demo.py`.
- [x] `protobuf.py::_create_device_point` is a 130-line `if "x" in ser` ladder. A
  `(column, proto_field, scale)` table + loop removes most of it and makes the typo class of bug
  (see P0) impossible. Replace `print(...)` with the logger.
- [x] `_data_structure.MAX_ROWS_PER_DEVICE = 300` caps buffered rows per device between two
  `get_data()` calls. Fine at 1 Hz with a 1 s drain, but silently drops rows for the 10/100 Hz
  serial modes. Document or make it a manager setting.

### 3.5 Logging

- [x] `get_naneos_logger()` attaches a `StreamHandler` (and optionally a `FileHandler`) to every
  module logger and hard-codes a level per module (`LEVEL_WARNING` in most, `INFO` in others).
  A library should add a `NullHandler` once and let the application configure levels and
  handlers; otherwise every message is printed twice as soon as the host app configures logging,
  and there is no single switch to turn on debug output. Keep `CustomFormatter` as an opt-in
  helper (`naneos.logger.enable_console_logging(level)`).
- [x] `stream_handler.terminator = "\r\n"` and the "create the log file at import time if the path
  exists" logic should go.

---

## 4. P3 - Hygiene, tooling, docs, tests

- [x] **Tooling config**: add `[tool.ruff]` (`line-length = 100`, select rules, `isort`) and
  `[tool.mypy]` to `pyproject.toml`; run `ruff format` once. Move `pytest` / `coverage` /
  `hypothesis` out of `[project.optional-dependencies].test` (unused, duplicates the `dev` group)
  or make `noxfile.py` use the dev group. Translate the German comment in `noxfile.py`.
- [x] **CI**: add a GitHub workflow for `ruff check`, `ruff format --check`, `mypy`, and the
  hardware-free tests. Mark hardware tests with `@pytest.mark.hardware` and skip them by default.
- [x] **Tests**: `test_00_demo_code.py` is a copy of `test_01::test_serial_manager`; `test_10_iotweb.py`
  is fully commented out (and its `NaneosUploadThread(data, ...)` call uses an old signature).
  Add real unit tests that need no hardware: serial line -> `NaneosDeviceDataPoint` casting for
  each data structure, `sort_and_clean_naneos_data`, `add_data_points_to_dict`, protobuf
  round-trip (`create_proto_device` on the pickles in `tests/data/`), BLE std/aux decoders
  (same pattern as the size-dist test), advertisement frame selection in `PartectorBleDecoder`.
- [x] **`__main__` blocks**: remove the demo code from `partector1/2/2_pro`,
  `partector_serial_manager`, `partector_ble_manager`, `partector_ble_connection`
  (`main`, `main_x`, `_map_sn_to_device`), `naneos_upload_thread`, `downloader`,
  `custom_logger`, `scanPartector`, `send_commands`. Keep one runnable example per feature in
  `examples/`. This also removes the private-API use in `examples/ble_adapter_demo.py`
  (`manager._is_bluetooth_adapter_available()`).
- [x] **Public API**: `naneos/__init__.py` is empty. Export `NaneosDeviceManager`,
  `PartectorSerialManager`, `PartectorBleManager`, `NaneosDeviceDataPoint`, `NaneosUploadThread`,
  `download_from_iotweb`, and a `__version__`.
- [x] **Naming**: `PartectorBluePrint` vs `PartectorBleDecoderBlueprint`, `scanPartector.py`,
  `_partectorCheckerThread.py`, `partectod_ble_decoder_aux_error.py`; German leftovers
  (`momentanwert`, `garagenbox`, `Nutzt BlueZ ...`).
- [x] **README / docs**: "Building executables" points at `demo/p1UploadTool.py` which does not
  exist; "Ideas for future development" lists the P2 BLE integration that is already done;
  `mkdocs` api-autonav documents every `__main__` demo. `installers/rp-naneos-uploader/
  uploader-script.py` and `examples/raspberry-pi-service.py` are the same script (one with the
  WiFi warning); keep one and reference it from the installer.
- [x] **Repo**: `uv.lock` still records the package at 1.1.10 while `pyproject.toml` says 1.1.17 (run `uv lock` and commit); `partector_data.pkl` in the root, `.DS_Store` files, `requirements.txt` in the
  installer with no version pin (a Pi installed today gets whatever is on PyPI).

---

## 5. Suggested order

1. **P0 bugs** in isolation, each its own commit, with a unit test where possible
   (data-structure mutation, `_fw` init, `__scan_port`, `usb_cc_voltage`, mypy).
2. **CS removal** (section 2) - mechanical, one commit, run the grep at the end.
3. **Tooling** (ruff config + format, mypy config, CI, hardware marker) so every following step
   is checked automatically.
4. **Data model move** (3.2) - touches every package but is mostly imports.
5. **Serial simplification** (3.1) - manager dicts and scan first (low risk), blueprint split
   last (needs devices on the desk to verify).
6. **BLE simplification** (3.3) - decoders first (pure functions, easy to test), then manager,
   then `_run()`.
7. **Manager / upload / logging** (3.4, 3.5).
8. **Hygiene** (section 4) as you go; the `__main__` removal can happen with each touched file.

## 6. Decisions needed from you

- Keep `DEV_TYPE` numeric values as an `IntEnum` with `3` reserved, or just drop 3?
- Are the 10 Hz / 100 Hz serial modes (`verb_freq` 2 / 3) still used by anyone? If not, the
  P2 mode handling and `MAX_ROWS_PER_DEVICE` can be simplified further.
- ~~Is `iotweb/download` (InfluxDB) still in use?~~ Now the optional extra `download`, see 7.5.

---

## 7. Next goal: one device API for serial and BLE

Added 2026-09-17, after 1.2.0. Goal: a customer writes to a device and sets its reading
frequency the same way on USB and BLE, through the managers, and the upload never exceeds 1 Hz
whatever the reading frequency is.

### 7.0 Where it stands

| | Serial | BLE |
|---|---|---|
| Write a command | `PartectorBlueprint.write_line(line, number_of_elem)`, only on a device you construct yourself | not implemented; the `write` / `read` characteristic UUIDs are declared in `partector_ble_connection.py` but never used |
| Set frequency | `set_verbose_freq(code)`; the value is a mode code, not Hz: 1 = 1 Hz, 2 = 10 Hz, 3 = 100 Hz, 6 = P2 Pro size distribution | fixed at the device's 1 Hz notify |
| Via the managers | `PartectorSerialManager` builds every device with defaults and keeps them private; a customer who opens the port themselves fights the manager for it | `PartectorBleConnection` is asyncio-internal, the caller gets no device handle |
| Threading | sync, two threads per device | asyncio inside a thread |
| 1 Hz upload cap | not enforced | holds only because BLE is 1 Hz anyway |

`NaneosDeviceManager` offers neither write nor rate. `examples/send_commands.py` opens a raw
`serial.Serial` and bypasses the library, which shows the write API is missing.

Facts from naneos (2026-09-17):

- The firmware accepts the same ASCII commands on the BLE write characteristic as on serial.
- The data rate cannot be changed over BLE; it is a serial-only feature.
- 100 Hz is not for productive use, but may be used for testing, so it should stay available.

### 7.1 P0 - Enforce the 1 Hz upload cap (done 2026-09-17)

- [x] **`to_upload_frame` rounded the ms index to seconds but never de-duplicated.** A 10 Hz serial
  device would have uploaded 10 points per second under the same timestamp. Rows of the same
  second are now merged by `frames.aggregate_duplicate_index()`: mean for measurements, bitwise
  OR for `device_status` (an error flagged in any sample survives), last known value for the
  rest. The 1 Hz case takes an early return and costs nothing. Tests with 10 Hz and 100 Hz frames
  in `test_09_upload_frames.py`.
- [x] **Buffer cap by time instead of rows.** `MAX_ROWS_PER_DEVICE = 300` was five minutes at 1 Hz
  but three seconds at 100 Hz. Correction to the first version of this list: it never hit
  `NaneosDeviceManager`, which drains the serial manager every second and has no cap of its own;
  it only hits a `PartectorSerialManager` used on its own and polled rarely. Serial frames are
  now capped at `MAX_BUFFER_SECONDS = 300`; the 1 Hz BLE point buffer keeps the row cap.
- [x] The output queue keeps the full-rate data for the customer; only the upload is capped.

### 7.2 P1 - Common device handle (done 2026-09-17)

- [x] `naneos.device.PartectorDevice`: `serial_number`, `device_type`, `firmware_version`,
  `connection_type`, `is_connected`, `sample_rate_hz`, `write(command)`,
  `query(command, timeout) -> list[str]`, `set_sample_rate(hz)`. Implemented by the serial
  classes and by `BlePartector`, the thread-safe handle of a BLE link. Exported from `naneos`.
- [x] All three managers have `get_devices()`. `NaneosDeviceManager` also has `get_device(sn)`
  (KeyError if not connected) and the shortcuts `write(sn, cmd)`, `query(sn, cmd)`,
  `set_sample_rate(sn, hz)`. A device reachable both ways is handed out with its USB connection.
- [x] `set_sample_rate` over BLE raises `NotSupportedError`; `sample_rate_hz` is 1.
- [x] `examples/send_commands.py` uses the manager and works on USB and BLE. Not run against a
  device here (it needs a command file); the old script sent each line with its line end, the
  new one strips it.
- [x] README section "Talking to a device".

Verified end to end on both devices: queries over BLE and USB through `NaneosDeviceManager`, two
threads querying one BLE device at once, 10 Hz on USB giving 104 rows per 10 s snapshot and 11
uploaded rows, never more than one per second.

### 7.3 P1 - Serial side (done 2026-09-17, verified on SN8617 P2 FW422 and SN8764 P2 Pro FW424)

- [x] **Blueprint split** (also closes the open item in 3.1). `SerialTransport` (open / write /
  readline / close, no threads), `PartectorBlueprint` (protocol and reader thread), and the scan
  talks to the transport directly, so `ScanPartector` and its two threads per port are gone.
  Deviations from the first plan:
  - The reader thread stays with the device instead of moving to the manager: reads block, so
    one thread per port is the simple correct design. The second (checker) thread is gone; the
    reader probes a device that was silent for 10 s itself.
  - A device no longer reconnects on its own. The old class rescanned all ports by serial number
    while the manager also dropped and re-found it. Now `is_connected` goes False and stays
    False; `PartectorSerialManager` re-finds the device on its next scan.
  - The constructor raises `ConnectionError` instead of returning a half-initialised object.
  - The transport can be injected, so the whole class is tested without hardware
    (`tests/fake_transport.py`, `test_04`).
- [x] `write(command)` and `query(command) -> list[str]` replace `write_line(line, number_of_elem)`.
  One command lock per device; verified with 4 threads x 30 queries while streaming at 100 Hz
  (40 of 40 rounds correct). Commands such as `X000n!`, `A0002!`, `opd0n!` send no
  acknowledgement, so a query cannot pick up a stale one; answers nobody waited for are drained.
- [x] Rates in Hz: `set_sample_rate(0 | 1 | 10 | 100)`, `sample_rate_hz`. The P2 Pro has
  `set_size_distribution(active, sample_rate_hz)`; in size distribution mode the device paces
  itself (one line about every 6 s), `sample_rate_hz` is None and `set_sample_rate` raises
  `NotSupportedError`. Found on hardware: a mode switch (`M000n!`) resets the pulse
  diagnostics output, so the settings must follow every switch, which also restarts the gain
  test settling time.
- [x] 100 Hz: nominal 1 / 10 / 100 Hz deliver 1.0 / 10.1 / 100 rows per second, nothing lost. The
  port is USB CDC, so the baudrate does not limit it. Lines are parsed in the reader thread and
  the point queue holds 1000 (ten seconds at 100 Hz).
- [x] Gain test and pulse diagnostics are arguments of `PartectorSerialManager` and
  `NaneosDeviceManager` (`serial_gain_test`, `serial_pulse_diagnostics`).
- [x] Done on the way, from 7.5: `close(reset_device=True)` plus an explicit `power_off()`;
  `get_data()` no longer holds the newest line back; `clear_data_cache()` and the
  `PartectorBluePrint` alias are gone.

### 7.4 P1 - BLE side (done 2026-09-17)

- [x] `PartectorBleConnection.write()` / `query()`, same ASCII commands as serial, one command in
  flight per device (asyncio lock). `BlePartector` hands calls from other threads to the
  manager's loop with `asyncio.run_coroutine_threadsafe`. What was measured on both devices:
  - `write` characteristic: property `write` (with response), 20 bytes per write. Longer
    commands raise `ValueError`; splitting them is untested.
  - `read` characteristic: property `indicate` only. A GATT read fails with "Read Not
    Permitted", so it is subscribed next to std / aux / size_dist. A device without it still
    gets its data link, commands then raise `ConnectionError`.
  - An answer is a 20 byte frame: the text, `\r\n`, padded with spaces. Frames are collected
    until the line end, so longer answers should work, but no command with one was found to
    verify it.
  - Latency 0.25 s to 1.0 s, so the query timeout is 2 s (serial: 0.25 s).
- [x] After every connect the link asks `f?` and `name?`: BLE points now carry
  `firmware_version`, and a P2 Pro is known as one right away instead of only after its first
  size distribution frame.
- [ ] Share the command layer between both transports. Left open on purpose: what is shared today
  is the interface; the only duplicated knowledge is the `name?` -> device type table (scan and
  BLE connection). Not worth a module yet.

### 7.5 P2 - Drop or simplify (done 2026-09-17, released as 2.0.0)

The migration table is in the README ("Migrating from 1.x to 2.0").

- [x] Compatibility shims removed: `scanPartector.py`, the `PartectorBluePrint` alias, `DEV_TYPE_*` /
  `CONN_TYPE_*`, the static DataFrame methods on the dataclass, the re-exports in
  `_data_structure.py`.
- [x] `scan_for_serial_partectors()`, the string `kind` argument and `DEVICE_KIND_NAMES` removed.
- [x] `serial_utils/` folded into `scan.py` (`list_serial_ports`).
- [x] `ConnectionType.ADVERTISEMENT` removed.
- [x] `NaneosUploadThread` is gone; `naneos/iotweb/upload.py` has plain functions
  (`upload_snapshot`, `to_upload_frame`, `build_combined_entry`, `build_body`).
- [x] `iotweb/download` is the optional extra `naneos-devices[download]`; a default install (the
  Pi) no longer pulls in `influxdb-client`. Importing it without the extra says what to install.
- [x] `NaneosDeviceManager` getter / setter pairs are properties: `use_serial`, `use_ble`,
  `upload_active`, `gathering_interval_seconds`, `pending_upload_count`,
  `seconds_until_next_snapshot`. The runtime toggling and `_sync_manager` stay (decided
  2026-09-17: unused today, but wanted for a GUI).
- [x] `get_connected_*_device_strings()` removed from all managers in favour of `get_devices()`;
  `BleLink.device_type` went with it (the connection knows its type).
- [x] `close(reset_device)` / `power_off()`, `get_data()` without the held back line: done in 7.3.
- [x] `upload_blocked_devices` is private; the serial manager's
  `get_gain_test_activating_devices()` is now `get_settling_serial_numbers()`.

### 7.6 Module layout (done 2026-09-17, part of 2.0.0)

Sections 0 to 7.5 use the module paths of their time. The layout since 2.0.0, grouped by
transport so that `usb/` and `ble/` mirror each other:

```
naneos/
  __init__.py   device.py   data_point.py   frames.py   manager.py   logger.py   cli.py
  usb/
    transport.py            shared by every USB device family
    partector/              device.py  layouts.py  scan.py  manager.py
  ble/
    partector/              connection.py  device.py  characteristics.py  advertisement.py
                            scanner.py  manager.py
  cloud/                    upload.py  download.py (optional extra)
  protobuf/                 protobuf.py  proto_v2.proto  proto_v2_pb2.py
```

- One subpackage per device family below each transport, because other devices will follow. What
  a new family can share goes one level up, like `usb/transport.py`. Everything in
  `ble/partector/` is Partector specific today (UUIDs, advertisement format, name filter); pull
  the generic parts up when the second BLE family arrives, not before.
- `usb/partector/device.py` holds the base class (`PartectorBlueprint` is now `UsbPartector`, next to
  `BlePartector`) and `Partector1` / `Partector2` / `Partector2Pro`.
- The one-file packages `manager/` and `logger/` are plain modules; `naneos.logger` and
  `from naneos.manager import NaneosDeviceManager` still import as before.
- `uploader.py` (the `naneos-uploader` command) is `cli.py`; `iotweb/` is `cloud/`; `protobuf/` stays
  its own package.
- `connection_type` stays `"serial"` in the data: the value is in stored frames and on the backend.
- The old -> new module table is in the README ("Migrating from 1.x to 2.0").

### 7.7 Upload format v2 (done 2026-09-17, part of 2.0.0)

- `proto_v2.proto` replaces `protoV1.proto` (deleted with its generated files). The upload goes to
  `.../dev/proto/v2/combined_data`. `UiCurve` (`/uicurve`) and `PulseForm` (`/pulseform`) exist in
  the schema but nothing in this package produces them yet.
- The schema carries the scale of every field as a field option, so `protobuf.py` builds its
  conversion table from the descriptor. Hand written are only: the six names that differ between
  frame and schema, the fields no device reports (`cs_status`, `electrometer_offset`,
  `electrometer_2_offset`) and the cs -> s unit factor of the two pulse delays. A test fails if
  any of these names stops existing in the schema or in `NaneosDeviceDataPoint`.
- Changes against v1 on the wire:
  - `electrometer_1/2_amplitude` go to `electrometer_amplitude(_2)` (scale 16). v1 had no amplitude
    field and sent them as `electrometer_1/2_offset` (scale 10). **Check that the backend reads
    the amplitude from the new field.**
  - New: `diffusion_current_average` -> `diffusion_current_avg`, `diffusion_current_max`.
    Still without a field: `corona_voltage_onset`, `hires_adc1/2`.
  - Every unsigned field clamps a negative reading to 0 (v1: three listed columns; any other
    negative value dropped the whole point).
  - The size distribution groups have no per-field presence: a group is sent when the row has at
    least one of its columns, missing columns then read back as 0.
- Verified against the dev endpoint: a live snapshot of SN8617 / SN8764 gave HTTP 200, "Wrote 9
  data point(s)". The recorded test frames (SN 666 / 777) give HTTP 200 but "Wrote 0": the dev
  backend does not store them (unknown serial numbers, presumably), so `test_10`'s upload test
  only proves that the request is accepted.

### 7.8 README and docs split (done 2026-09-17)

- `README.md` (also the PyPI page) only explains the device manager: quick start, queue hand-off,
  runtime controls, talking to a device, logging. All links are absolute, because PyPI does not
  resolve relative ones. Every section names the example that shows it.
- `docs/`: `user-guide/devices.md` (handles, rate, P2 Pro modes, diagnostics),
  `user-guide/logging.md`, `user-guide/migration-2.0.md`, `user-guide/raspberry-pi-setup.md`,
  `development/contributing.md` (tests, hardware testing before a merge, protobuf, executables).
- `examples/`: one script per README section (`quick_start`, `queue_handoff`, `runtime_controls`,
  `device_commands`) replaces `demo.py`. All examples were run against SN8617 / SN8764;
  `send_commands.py` only with a file that has no line to send, `download_iotweb.py` only up to
  its missing-token message.

### 7.9 Live data stream (done 2026-09-17)

- Before: data only left `NaneosDeviceManager` as snapshots, every 10 s at best; internally it was
  polled once per second through two layers.
- `register_live_queue(queue)` delivers every `NaneosDeviceDataPoint` as it arrives. The points are
  pushed, not polled: `UsbPartector`, `PartectorSerialManager`, `PartectorBleConnection` and
  `PartectorBleManager` take an optional `point_listener`; the device manager passes its
  `_on_live_point`. The pull API (`get_data()`), the snapshots and the upload are unchanged.
- Rules: BLE points of a device that is also connected over USB are skipped (same preference as the
  snapshots); a full queue drops its oldest point and counts it (`live_points_dropped`); a
  listener that raises is logged and does not stop a reader thread or a BLE link.
- Points are dataclasses, not DataFrames: a DataFrame per point is the most expensive thing this
  library does on a Pi.
- Measured: SN8617 at 100 Hz gave 501 live points in 5 s with both BLE links up (no BLE
  duplicates), about 1 ms after the line was read, 0 dropped, while the 10 s snapshot still had
  its 1003 rows. With USB switched off at runtime both devices continued at 1 Hz over BLE.

### 7.10 What is left

Nothing from this section. Still open from earlier sections: the `[ ]` item in 7.4 (shared
command layer, left open on purpose) and the hardware check of the Windows-only BLE branches
(3.3).

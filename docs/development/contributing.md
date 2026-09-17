# Development

Set up with [uv](https://docs.astral.sh/uv/): `uv sync` installs the package with the dev tools.
`REFACTORING.md` in the repository root records the design decisions and hardware findings.

## Testing
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


### Hardware testing before a merge
Changes that touch the serial or BLE code are tested on real devices before they reach `master`:

1. Point the `release_test` branch at the feature branch: `git branch -f release_test <feature> && git push -f origin release_test`.
2. Raspberry Pi: `curl -fsSL .../installers/install.sh | sudo bash -s -- --ref release_test` (see [Raspberry Pi Setup](../user-guide/raspberry-pi-setup.md)), then watch `journalctl -u naneos_uploader.service -f`.
3. Windows / macOS: in any virtual environment
   `pip install "https://github.com/naneos-org/python-naneos-devices/archive/release_test.tar.gz"`
   and run `pytest -m hardware` from a checkout with the devices attached. To switch an existing
   environment to another branch with the same version number, add `--force-reinstall --no-deps`;
   pip otherwise keeps what is installed.
4. When it works, open the pull request from the feature branch to `master`, merge, tag the release.

Contributions are welcome! If you encounter any issues or have suggestions for improvements, please submit an issue on the [issue tracker](https://github.com/naneos-org/python-naneos-devices/issues).

Please make sure to adhere to the coding style and conventions used in the repository and provide appropriate tests and documentation for your changes.


## Protobuf
The upload format is defined in `src/naneos/protobuf/proto_v2.proto` (shared with the backend, never
renumber fields). Regenerate the Python module and the stub in that directory with:
```bash
protoc -I=. --python_out=. --pyi_out=. ./proto_v2.proto
```


## Building executables
Sometimes you want to build an executable for a customer with your custom script.
The build must happen on the same OS as the target OS.
For example if you want to build an executable for windows you need to build it on Windows.

```bash
pyinstaller examples/quick_start.py --console --noconfirm --clean --onefile
```


# Development

Set up with [uv](https://docs.astral.sh/uv/): `uv sync` installs the package with the dev tools.
`REFACTORING.md` in the repository root records the design decisions and hardware findings. `IDEAS.md` next to it collects planned features that are not started yet.

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

CI runs the tests on every supported Python version (3.11 to 3.14). To try another one locally:
```bash
uv run --python 3.13 pytest
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
4. When it works, open the pull request from the feature branch to `master` and merge. Releasing is described [below](#releasing).

Contributions are welcome! If you encounter any issues or have suggestions for improvements, please submit an issue on the [issue tracker](https://github.com/naneos-org/python-naneos-devices/issues).

Please make sure to adhere to the coding style and conventions used in the repository and provide appropriate tests and documentation for your changes.


## Releasing
The version lives only in `pyproject.toml` and is changed with `uv version --bump`. Every push to
`master` runs `.github/workflows/release.yml`: when the version has no `v<version>` tag yet, it runs
the checks, builds, publishes to PyPI and then creates the tag. Never tag by hand, and do not delete
a tag: it is how the workflow knows that a version is released. There are no GitHub releases, PyPI
holds them.

Every version goes to PyPI. What users get depends on its name:

| Version | Example | On PyPI |
|---|---|---|
| release candidate (`rc`, also `a`, `b`, `.dev`) | `2.0.4rc1` | pre-release: only installed when asked for (`==2.0.4rc1` or `--pre`) |
| final | `2.0.4` | what `pip install naneos-devices` installs |

The rc suffix follows the version number directly, without dot or dash: `2.0.4rc1`, not
`2.0.4-rc1` or `2.0.4.rc1`. `uv version` writes it correctly, so do not edit the number by hand.

Example: release `2.0.4`, starting from `2.0.3`, with a release candidate first.
```bash
uv version --bump patch --bump rc   # 2.0.3    -> 2.0.4rc1
git commit -am "v2.0.4rc1" && git push

uv version --bump rc                # 2.0.4rc1 -> 2.0.4rc2, only if rc1 needed a fix
git commit -am "v2.0.4rc2" && git push

uv version --bump stable            # 2.0.4rc2 -> 2.0.4, the release users get
git commit -am "v2.0.4" && git push
```

Use `--bump stable` to finish a release candidate. `--bump patch` on `2.0.4rc2` gives `2.0.5` and
skips `2.0.4`. For a minor or major release replace `patch` in the first command
(`uv version --bump minor --bump rc` gives `2.1.0rc1`); without a release candidate,
`uv version --bump patch` goes straight to the final version. Add `--dry-run` to see the result without changing anything.

Install a release candidate:
```bash
pip install naneos-devices==2.0.4rc1
```
On a Raspberry Pi the installer does this with `--version 2.0.4rc1`, or with `--pre` for the newest
version including pre-releases, see [Raspberry Pi Setup](../user-guide/raspberry-pi-setup.md).

Release candidates stay in the PyPI history for good, so cut one when the packaged build needs
testing. For testing code on a device before a merge, use the `release_test` branch (above); that
needs no version number.

A version number can never be uploaded twice, not even after deleting it. If a release fails halfway,
fix the cause and start the `release` workflow again from the Actions tab; files that are already
uploaded are skipped.


## Protobuf
The upload format is defined in `src/naneos/protobuf/proto_v2.proto` (shared with the backend, never
renumber fields). Regenerate the Python module and the stub in that directory with:
```bash
protoc -I=. --python_out=. --pyi_out=. ./proto_v2.proto
```
Then raise the `protobuf` floor in `pyproject.toml` to the `Protobuf Python Version` in the header of
`proto_v2_pb2.py`. The generated code refuses to import under an older runtime, and the installer
keeps a protobuf that is already installed as long as it meets the floor. `tests/test_05_protobuf.py`
checks this.


## Building executables
Sometimes you want to build an executable for a customer with your custom script.
The build must happen on the same OS as the target OS.
For example if you want to build an executable for windows you need to build it on Windows.

```bash
pyinstaller examples/quick_start.py --console --noconfirm --clean --onefile
```


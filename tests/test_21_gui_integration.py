"""Hardware-free tests for how the tray app fits into each OS (no Qt needed).

Nothing here touches the real home directory, registry or LaunchAgents.
"""

import configparser
import plistlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from naneos.gui import integration
from naneos.gui.integration import (
    BUNDLE_ID,
    LinuxAutostart,
    MacAutostart,
    WindowsAutostart,
    _desktop_quote,
    entry_point,
    get_autostart,
    install_integration,
    install_macos_bundle,
    launch_command,
    linux_menu_entry_path,
    log_dir,
    macos_bundle_path,
    remove_integration,
)

# ---------------------------------------------------------------- paths


def test_log_dir_per_platform(tmp_path) -> None:
    assert log_dir("darwin", {}, tmp_path) == tmp_path / "Library" / "Logs" / "naneos-devices"

    assert log_dir("win32", {"LOCALAPPDATA": r"C:\Users\x\AppData\Local"}, tmp_path) == (
        Path(r"C:\Users\x\AppData\Local") / "naneos" / "naneos-devices" / "Logs"
    )
    assert log_dir("win32", {}, tmp_path) == (
        tmp_path / "AppData" / "Local" / "naneos" / "naneos-devices" / "Logs"
    )

    assert log_dir("linux", {}, tmp_path) == tmp_path / ".local" / "state" / "naneos-devices"
    assert log_dir("linux", {"XDG_STATE_HOME": str(tmp_path / "state")}, tmp_path) == (
        tmp_path / "state" / "naneos-devices"
    )


def test_entry_point_is_next_to_the_running_python(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bin" / "python"))
    assert entry_point("linux") == tmp_path / "bin" / "naneos-gui"
    assert entry_point("darwin") == tmp_path / "bin" / "naneos-gui"
    assert entry_point("win32") == tmp_path / "bin" / "naneos-gui.exe"


def test_launch_command_uses_the_script_or_falls_back_to_python_dash_m(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    assert launch_command() == [str(tmp_path / "python"), "-m", "naneos.gui"]

    (tmp_path / "naneos-gui").write_text("#!/bin/sh\n")
    monkeypatch.setattr(integration, "current_platform", lambda: "linux")
    assert launch_command() == [str(tmp_path / "naneos-gui")]


# ---------------------------------------------------------------- Linux


def _parse_desktop(path: Path) -> configparser.SectionProxy:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]  # keys are case sensitive
    parser.read(path, encoding="utf-8")
    return parser["Desktop Entry"]


def test_desktop_quote() -> None:
    assert _desktop_quote("/home/x/.local/bin/naneos-gui") == "/home/x/.local/bin/naneos-gui"
    assert _desktop_quote("/home/my user/bin/naneos-gui") == '"/home/my user/bin/naneos-gui"'
    assert _desktop_quote("100%") == "100%%"
    assert _desktop_quote('a"b') == '"a\\\\"b"'
    assert _desktop_quote("a$b") == '"a\\\\$b"'


def test_linux_autostart_writes_and_removes_the_desktop_file(tmp_path) -> None:
    autostart = LinuxAutostart(["/opt/my tool/naneos-gui"], environ={}, home=tmp_path)
    path = tmp_path / ".config" / "autostart" / "naneos-devices.desktop"
    assert not autostart.enabled()

    autostart.enable()

    assert autostart.enabled()
    entry = _parse_desktop(path)
    assert entry["Type"] == "Application"
    assert entry["Name"] == "Naneos Devices"
    assert entry["Exec"] == '"/opt/my tool/naneos-gui"'
    assert entry["Terminal"] == "false"
    assert entry["X-GNOME-Autostart-enabled"] == "true"
    assert Path(entry["Icon"]).exists()

    autostart.disable()
    assert not autostart.enabled()
    autostart.disable()  # already gone: no error


def test_linux_autostart_honours_xdg_config_home(tmp_path) -> None:
    autostart = LinuxAutostart(
        ["/x/naneos-gui"], environ={"XDG_CONFIG_HOME": str(tmp_path / "cfg")}, home=tmp_path
    )
    autostart.enable()
    assert (tmp_path / "cfg" / "autostart" / "naneos-devices.desktop").exists()


def test_linux_menu_entry_is_installed_and_removed(tmp_path) -> None:
    written = install_integration("linux", ["/x/naneos-gui"], {}, tmp_path)

    path = tmp_path / ".local" / "share" / "applications" / "naneos-devices.desktop"
    assert written == [path]
    entry = _parse_desktop(path)
    assert entry["Exec"] == "/x/naneos-gui"
    assert "X-GNOME-Autostart-enabled" not in entry  # the menu entry is not the autostart one

    assert linux_menu_entry_path({}, tmp_path) == path
    remove_integration("linux", {}, tmp_path)
    assert not path.exists()


# ---------------------------------------------------------------- Windows


class FakeWinreg:
    """Just enough of the winreg module: one key, values in a dict."""

    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def _key(self) -> SimpleNamespace:
        class Key:
            def __enter__(self_) -> "Key":
                return self_

            def __exit__(self_, *exc: object) -> None:
                return None

        return Key()  # type: ignore[return-value]

    def OpenKey(self, root, path, reserved=0, access=0):  # noqa: N802
        assert root == self.HKEY_CURRENT_USER and path.endswith(r"CurrentVersion\Run")
        return self._key()

    CreateKey = lambda self, root, path: self.OpenKey(root, path)  # noqa: E731,N815

    def QueryValueEx(self, key, name):  # noqa: N802
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        assert kind == self.REG_SZ
        self.values[name] = value

    def DeleteValue(self, key, name):  # noqa: N802
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_windows_autostart_uses_the_run_key() -> None:
    registry = FakeWinreg()
    autostart = WindowsAutostart([r"C:\Users\my user\naneos-gui.exe"], registry)
    assert not autostart.enabled()

    autostart.enable()

    assert autostart.enabled()
    assert registry.values == {"NaneosDevices": r'"C:\Users\my user\naneos-gui.exe"'}

    autostart.disable()
    assert not autostart.enabled()
    autostart.disable()  # already gone: no error


# ---------------------------------------------------------------- macOS


@pytest.fixture
def fake_launcher(monkeypatch, tmp_path) -> Path:
    """A stand-in for the compiled launcher, so the tests also run on Linux and Windows."""
    binary = tmp_path / "package" / "naneos-launcher"
    binary.parent.mkdir()
    binary.write_bytes(b"launcher v1")
    monkeypatch.setattr(integration, "launcher_binary", lambda: binary)
    return binary


@pytest.fixture
def tools(monkeypatch) -> list[list[str]]:
    """Record the helper tools (xattr, codesign) instead of running them."""
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(integration.subprocess, "run", fake_run)
    return calls


def test_macos_bundle_has_what_bluetooth_needs(fake_launcher, tools, tmp_path) -> None:
    app = install_macos_bundle(["/tool/bin/naneos-gui"], tmp_path)

    assert app == macos_bundle_path(tmp_path) == tmp_path / "Applications" / "Naneos Devices.app"
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == BUNDLE_ID
    assert info["CFBundleExecutable"] == "naneos-launcher"
    assert info["LSUIElement"] is True
    assert "Bluetooth" in info["NSBluetoothAlwaysUsageDescription"]

    launcher = app / "Contents" / "MacOS" / "naneos-launcher"
    assert launcher.read_bytes() == b"launcher v1"
    assert launcher.stat().st_mode & 0o111
    script = app / "Contents" / "Resources" / "launch.sh"
    assert script.read_text() == '#!/bin/sh\nexec /tool/bin/naneos-gui "$@"\n'
    assert script.stat().st_mode & 0o111


def test_macos_launch_script_quotes_the_command(fake_launcher, tools, tmp_path) -> None:
    app = install_macos_bundle(["/my tool/bin/python", "-m", "naneos.gui"], tmp_path)

    script = (app / "Contents" / "Resources" / "launch.sh").read_text()
    assert script == "#!/bin/sh\nexec '/my tool/bin/python' -m naneos.gui \"$@\"\n"


def test_macos_bundle_is_signed_once_and_left_alone_afterwards(
    fake_launcher, tools, tmp_path
) -> None:
    app = install_macos_bundle(["/tool/bin/naneos-gui"], tmp_path)
    signed = [c for c in tools if c[0] == "codesign" and "--sign" in c]
    assert len(signed) == 1
    assert signed[0][-1] == str(app)
    assert "--identifier" in signed[0] and BUNDLE_ID in signed[0]

    tools.clear()
    launcher = app / "Contents" / "MacOS" / "naneos-launcher"
    before = launcher.stat().st_mtime_ns
    install_macos_bundle(["/tool/bin/naneos-gui"], tmp_path)

    assert launcher.stat().st_mtime_ns == before
    assert not [c for c in tools if c[0] == "codesign" and "--sign" in c]


def test_macos_bundle_is_signed_again_when_the_command_changes(
    fake_launcher, tools, tmp_path
) -> None:
    install_macos_bundle(["/tool/bin/naneos-gui"], tmp_path)
    tools.clear()

    app = install_macos_bundle(["/other/bin/naneos-gui"], tmp_path)

    assert "/other/bin/naneos-gui" in (app / "Contents" / "Resources" / "launch.sh").read_text()
    assert [c for c in tools if c[0] == "codesign" and "--sign" in c]


def test_macos_bundle_is_repaired_when_its_signature_is_not_valid(
    fake_launcher, monkeypatch, tmp_path
) -> None:
    install_macos_bundle(["/tool/bin/naneos-gui"], tmp_path)
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 1 if "--verify" in command else 0, "", "")

    monkeypatch.setattr(integration.subprocess, "run", fake_run)
    install_macos_bundle(["/tool/bin/naneos-gui"], tmp_path)

    assert [c for c in calls if c[0] == "codesign" and "--sign" in c]


def test_macos_launcher_is_only_copied_for_a_new_launcher_version(
    fake_launcher, tools, monkeypatch, tmp_path
) -> None:
    app = install_macos_bundle(["/tool/bin/naneos-gui"], tmp_path)
    launcher = app / "Contents" / "MacOS" / "naneos-launcher"

    fake_launcher.write_bytes(b"launcher v2")
    install_macos_bundle(["/tool/bin/naneos-gui"], tmp_path)
    assert launcher.read_bytes() == b"launcher v1"  # same version: not replaced

    monkeypatch.setattr(integration, "LAUNCHER_VERSION", "2")
    install_macos_bundle(["/tool/bin/naneos-gui"], tmp_path)
    assert launcher.read_bytes() == b"launcher v2"


def test_macos_bundle_without_a_launcher_is_an_error(monkeypatch, tools, tmp_path) -> None:
    monkeypatch.setattr(integration, "launcher_binary", lambda: tmp_path / "missing")
    with pytest.raises(FileNotFoundError, match="launcher"):
        install_macos_bundle(["/tool/bin/naneos-gui"], tmp_path)


def test_macos_autostart_is_a_launch_agent_that_opens_the_bundle(
    fake_launcher, tools, tmp_path
) -> None:
    autostart = MacAutostart(["/tool/bin/naneos-gui"], tmp_path)
    assert not autostart.enabled()

    autostart.enable()

    assert autostart.enabled()
    agent = plistlib.loads(autostart.plist_path.read_bytes())
    assert autostart.plist_path == tmp_path / "Library" / "LaunchAgents" / f"{BUNDLE_ID}.plist"
    assert agent["Label"] == BUNDLE_ID
    assert agent["RunAtLoad"] is True
    assert "KeepAlive" not in agent  # Quit in the menu must stay quit
    assert agent["ProgramArguments"] == [
        "/usr/bin/open",
        "-g",
        "-a",
        str(macos_bundle_path(tmp_path)),
    ]
    assert macos_bundle_path(tmp_path).exists()  # enabling installs the bundle it opens

    autostart.disable()
    assert not autostart.enabled()
    autostart.disable()  # already gone: no error


def test_remove_integration_deletes_the_macos_bundle(fake_launcher, tools, tmp_path) -> None:
    app = install_integration("darwin", ["/tool/bin/naneos-gui"], {}, tmp_path)[0]
    assert app.exists()

    remove_integration("darwin", {}, tmp_path)

    assert not app.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="needs codesign and the real launcher")
def test_macos_bundle_with_the_real_launcher_is_valid_and_runs_its_child(tmp_path) -> None:
    child = tmp_path / "child.sh"
    child.write_text('#!/bin/sh\necho "$@" > "$0.out"\nexit 3\n')
    child.chmod(0o755)

    app = install_macos_bundle([str(child)], tmp_path)

    verify = subprocess.run(["codesign", "--verify", "--strict", str(app)], capture_output=True)
    assert verify.returncode == 0, verify.stderr
    run = subprocess.run(
        [str(app / "Contents" / "MacOS" / "naneos-launcher"), "-psn_0_1", "a", "b"]
    )
    assert run.returncode == 3  # the exit status of the child comes through
    assert Path(str(child) + ".out").read_text().strip() == "a b"  # without the -psn_ argument


# ---------------------------------------------------------------- the factory


def test_get_autostart_picks_the_class_of_the_platform(tmp_path) -> None:
    command = ["/x/naneos-gui"]
    assert isinstance(get_autostart("darwin", command, {}, tmp_path), MacAutostart)
    assert isinstance(get_autostart("win32", command, {}, tmp_path), WindowsAutostart)
    assert isinstance(get_autostart("linux", command, {}, tmp_path), LinuxAutostart)


def test_windows_needs_no_integration_from_python(tmp_path) -> None:
    assert install_integration("win32", ["x"], {}, tmp_path) == []
    remove_integration("win32", {}, tmp_path)  # nothing to remove, no error

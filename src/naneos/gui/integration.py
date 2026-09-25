"""How the tray app fits into each operating system, without Qt.

- where it logs,
- how it starts at login (LaunchAgent, Run key, XDG autostart),
- the macOS app bundle that lets Bluetooth ask for permission in its own name,
- the Linux application menu entry.

Everything takes the home directory, the environment and (on Windows) the
registry as optional arguments, so the tests never touch the real ones.
"""

import importlib
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from naneos.logger import get_naneos_logger

logger = get_naneos_logger("naneos.gui.integration")

APP_NAME = "Naneos Devices"
BUNDLE_ID = "org.naneos.devices"
COMMAND_NAME = "naneos-gui"

# The macOS app bundle. Bump the launcher version when macos/launcher.c changes:
# a new binary is a new code signature, so macOS asks for Bluetooth access again.
LAUNCHER_NAME = "naneos-launcher"
LAUNCHER_VERSION = "1"
BLUETOOTH_USAGE = "Naneos Devices reads your Partector particle counters over Bluetooth."

_WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_WINDOWS_RUN_VALUE = "NaneosDevices"
_DESKTOP_FILE = "naneos-devices.desktop"


def current_platform() -> str:
    """ "darwin", "win32" or "linux" (every other Unix counts as linux)."""
    if sys.platform in ("darwin", "win32"):
        return sys.platform
    return "linux"


def resources_dir() -> Path:
    return Path(__file__).parent / "resources"


def icon_file(suffix: str = "png") -> Path:
    return resources_dir() / f"naneos_icon.{suffix}"


def launcher_binary() -> Path:
    return resources_dir() / "macos" / LAUNCHER_NAME


def _home(home: Path | None) -> Path:
    return home if home is not None else Path.home()


def _environ(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return environ if environ is not None else os.environ


def log_dir(
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Where the tray app writes naneos-devices.log."""
    platform = platform or current_platform()
    env, home = _environ(environ), _home(home)
    if platform == "darwin":
        return home / "Library" / "Logs" / "naneos-devices"
    if platform == "win32":
        base = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
        return base / "naneos" / "naneos-devices" / "Logs"
    return Path(env.get("XDG_STATE_HOME") or home / ".local" / "state") / "naneos-devices"


def entry_point(platform: str | None = None) -> Path:
    """The naneos-gui next to the running python, i.e. inside the environment that
    `uv tool install` made. That path stays the same when the tool is reinstalled."""
    name = COMMAND_NAME + (".exe" if (platform or current_platform()) == "win32" else "")
    return Path(sys.executable).with_name(name)


def launch_command() -> list[str]:
    """The command that starts the tray app: the installed script, or `python -m
    naneos.gui` when run from a checkout."""
    entry = entry_point()
    if entry.exists():
        return [str(entry)]
    return [sys.executable, "-m", "naneos.gui"]


def _write_if_changed(path: Path, data: bytes, mode: int = 0o644) -> bool:
    """Write a file unless it already holds exactly this. Returns whether it wrote.

    Keeping an identical file untouched matters for the macOS launcher: macOS ties
    the Bluetooth permission to its code signature, and a rewrite of the same
    bytes is harmless but a needless risk.
    """
    try:
        # Windows has no POSIX file modes to compare.
        mode_is_right = os.name == "nt" or (path.stat().st_mode & 0o777) == mode
        if mode_is_right and path.read_bytes() == data:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.chmod(mode)
    os.replace(tmp, path)
    return True


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


class Autostart(ABC):
    """Start the tray app when the user logs in."""

    @abstractmethod
    def enabled(self) -> bool: ...

    @abstractmethod
    def enable(self) -> None: ...

    @abstractmethod
    def disable(self) -> None: ...


# ---------------------------------------------------------------- macOS


def macos_bundle_path(home: Path | None = None) -> Path:
    return _home(home) / "Applications" / f"{APP_NAME}.app"


def _macos_info_plist() -> bytes:
    return plistlib.dumps(
        {
            "CFBundleIdentifier": BUNDLE_ID,
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleExecutable": LAUNCHER_NAME,
            "CFBundleIconFile": icon_file("icns").stem,
            "CFBundlePackageType": "APPL",
            "CFBundleInfoDictionaryVersion": "6.0",
            "CFBundleVersion": LAUNCHER_VERSION,
            "CFBundleShortVersionString": LAUNCHER_VERSION,
            "LSMinimumSystemVersion": "12.0",
            # The launcher itself has no windows: no Dock icon, no menu bar of its own.
            "LSUIElement": True,
            "NSBluetoothAlwaysUsageDescription": BLUETOOTH_USAGE,
        },
        sort_keys=True,
    )


def install_macos_bundle(command: list[str], home: Path | None = None) -> Path:
    """Write ~/Applications/Naneos Devices.app and return its path.

    macOS asks for Bluetooth access on behalf of the "responsible" app, the one
    at the top of the process chain. A python started at login has no
    Info.plist with a usage text, so CoreBluetooth would kill it or never ask.
    So the bundle holds a small launcher that starts python as its child; the
    child inherits the launcher as the responsible app (see macos/launcher.c).

    Idempotent: files that already hold the right content are left alone, and the
    bundle is only signed again when it changed or its signature is not valid.
    The signature is ad-hoc and the same for the same content, so an update of
    the package does not make macOS ask for Bluetooth access again.
    """
    binary = launcher_binary()
    if not binary.exists():
        raise FileNotFoundError(f"the macOS launcher is missing from the package: {binary}")

    app = macos_bundle_path(home)
    contents = app / "Contents"
    installed_launcher = contents / "MacOS" / LAUNCHER_NAME
    script = "#!/bin/sh\nexec " + " ".join(shlex.quote(part) for part in command) + ' "$@"\n'

    # The installed launcher carries the signature of the bundle, so it never equals the
    # one in the package: copy it only for a new launcher version, not on every install.
    new_launcher = (
        not installed_launcher.exists()
        or _bundle_version(contents / "Info.plist") != LAUNCHER_VERSION
    )
    changed = [
        _write_if_changed(contents / "Info.plist", _macos_info_plist()),
        _write_if_changed(contents / "Resources" / "launch.sh", script.encode(), 0o755),
    ]
    if new_launcher:
        changed.append(_write_if_changed(installed_launcher, binary.read_bytes(), 0o755))
    icns = icon_file("icns")
    if icns.exists():
        changed.append(_write_if_changed(contents / "Resources" / icns.name, icns.read_bytes()))

    if any(changed):
        logger.info(f"Wrote the macOS app bundle {app}")
        # Files copied from a downloaded package can carry attributes codesign refuses.
        _run(["xattr", "-cr", str(app)])
    if any(changed) or not _codesign_is_valid(app):
        _run(["codesign", "--force", "--sign", "-", "--identifier", BUNDLE_ID, str(app)])
    return app


def _bundle_version(info_plist: Path) -> str | None:
    try:
        return str(plistlib.loads(info_plist.read_bytes()).get("CFBundleVersion"))
    except (OSError, ValueError):
        return None


def _run(command: list[str]) -> bool:
    """Run a helper tool. A missing or failing tool is logged, not fatal."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as e:
        logger.warning(f"Cannot run {command[0]}: {e}")
        return False
    if result.returncode != 0:
        logger.warning(f"{' '.join(command[:2])} failed: {result.stderr.strip()}")
    return result.returncode == 0


def _codesign_is_valid(app: Path) -> bool:
    try:
        result = subprocess.run(
            ["codesign", "--verify", "--strict", str(app)], capture_output=True, check=False
        )
    except OSError:
        return True  # no codesign, nothing we could do about it
    return result.returncode == 0


class MacAutostart(Autostart):
    """A LaunchAgent that opens the app bundle at login (`open -g -a`).

    It takes effect at the next login. `open` goes through LaunchServices, so the
    start looks like a double click and the bundle stays the responsible app.
    """

    def __init__(self, command: list[str], home: Path | None = None) -> None:
        self._command = command
        self._home = _home(home)

    @property
    def plist_path(self) -> Path:
        return self._home / "Library" / "LaunchAgents" / f"{BUNDLE_ID}.plist"

    def enabled(self) -> bool:
        return self.plist_path.exists()

    def enable(self) -> None:
        bundle = install_macos_bundle(self._command, self._home)
        agent = plistlib.dumps(
            {
                "Label": BUNDLE_ID,
                "ProgramArguments": ["/usr/bin/open", "-g", "-a", str(bundle)],
                "RunAtLoad": True,
                "LimitLoadToSessionType": "Aqua",
            },
            sort_keys=True,
        )
        _write_if_changed(self.plist_path, agent)

    def disable(self) -> None:
        _unlink(self.plist_path)


# ---------------------------------------------------------------- Windows


class WindowsAutostart(Autostart):
    """A value in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run (no admin needed)."""

    def __init__(self, command: list[str], registry: Any = None) -> None:
        self._command = command
        self._registry = registry

    def _winreg(self) -> Any:
        return self._registry or importlib.import_module("winreg")

    def enabled(self) -> bool:
        winreg = self._winreg()
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _WINDOWS_RUN_KEY, 0, winreg.KEY_READ
            ) as k:
                value, _ = winreg.QueryValueEx(k, _WINDOWS_RUN_VALUE)
        except OSError:
            return False
        return bool(value)

    def enable(self) -> None:
        winreg = self._winreg()
        command = subprocess.list2cmdline(self._command)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _WINDOWS_RUN_KEY) as key:
            winreg.SetValueEx(key, _WINDOWS_RUN_VALUE, 0, winreg.REG_SZ, command)

    def disable(self) -> None:
        winreg = self._winreg()
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, _WINDOWS_RUN_VALUE)
        except OSError:
            pass  # already gone


# ---------------------------------------------------------------- Linux


def _desktop_quote(argument: str) -> str:
    """One argument of an Exec= line, as the Desktop Entry Specification wants it."""
    argument = argument.replace("%", "%%")
    if argument and not any(c in argument for c in " \t\n\"'\\<>~|&;$*?#()`"):
        return argument
    quoted = "".join("\\" + c if c in '"`$\\' else c for c in argument)
    # The string escape (backslash) is applied before the quoting rule, so it is doubled.
    return '"' + quoted.replace("\\", "\\\\") + '"'


def _desktop_entry(command: list[str], autostart: bool) -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={APP_NAME}",
        "Comment=Shows and uploads the data of your naneos Partector devices",
        "Exec=" + " ".join(_desktop_quote(part) for part in command),
        f"Icon={icon_file('png')}",
        "Terminal=false",
        "Categories=Utility;",
    ]
    if autostart:
        lines += ["X-GNOME-Autostart-enabled=true", "X-GNOME-Autostart-Delay=5"]
    return "\n".join(lines) + "\n"


class LinuxAutostart(Autostart):
    """~/.config/autostart/naneos-devices.desktop (XDG autostart)."""

    def __init__(
        self,
        command: list[str],
        environ: Mapping[str, str] | None = None,
        home: Path | None = None,
    ) -> None:
        self._command = command
        self._environ = _environ(environ)
        self._home = _home(home)

    @property
    def desktop_path(self) -> Path:
        config = Path(self._environ.get("XDG_CONFIG_HOME") or self._home / ".config")
        return config / "autostart" / _DESKTOP_FILE

    def enabled(self) -> bool:
        return self.desktop_path.exists()

    def enable(self) -> None:
        _write_if_changed(self.desktop_path, _desktop_entry(self._command, True).encode())

    def disable(self) -> None:
        _unlink(self.desktop_path)


def linux_menu_entry_path(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    data = Path(_environ(environ).get("XDG_DATA_HOME") or _home(home) / ".local" / "share")
    return data / "applications" / _DESKTOP_FILE


# ---------------------------------------------------------------- all platforms


def get_autostart(
    platform: str | None = None,
    command: list[str] | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Autostart:
    platform = platform or current_platform()
    command = command or launch_command()
    if platform == "darwin":
        return MacAutostart(command, home)
    if platform == "win32":
        return WindowsAutostart(command)
    return LinuxAutostart(command, environ, home)


def install_integration(
    platform: str | None = None,
    command: list[str] | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> list[Path]:
    """Make the app startable from the desktop. Returns what was written.

    macOS: the app bundle. Linux: the application menu entry. Windows: nothing
    here, the installer script makes the Start Menu shortcut.
    """
    platform = platform or current_platform()
    command = command or launch_command()
    if platform == "darwin":
        return [install_macos_bundle(command, home)]
    if platform == "linux":
        path = linux_menu_entry_path(environ, home)
        _write_if_changed(path, _desktop_entry(command, False).encode())
        return [path]
    return []


def remove_integration(
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> None:
    platform = platform or current_platform()
    if platform == "darwin":
        shutil.rmtree(macos_bundle_path(home), ignore_errors=True)
    elif platform == "linux":
        _unlink(linux_menu_entry_path(environ, home))

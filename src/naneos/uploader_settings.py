"""Settings of the `naneos-uploader` service from a text file on the SD card.

A customer without SSH can still change the options of the service and add a
WiFi network: the boot partition of a Raspberry Pi is FAT and opens on any PC.
Two files live there:

* ``naneos-uploader-change.txt``: the customer writes ``OPTIONS=--interval 60``
  (the same options as on the command line), ``WIFI_SSID=`` plus
  ``WIFI_PASSWORD=``, and/or ``AUTO_UPDATE=on|off``. The next boot applies the
  lines, then resets the file to its commented template, which also removes
  the password from the card.
* ``naneos-uploader-current.txt``: written at every boot, shows the options the
  service runs with and the WiFi networks the Pi knows, plus an error if the
  last change was rejected. Never the password.

"Applied" means, for the options, written to an environment file that the
systemd unit reads (``EnvironmentFile=``) and expands in its ``ExecStart``:

    NANEOS_UPLOADER_OPTIONS=--interval 60

and for WiFi, a NetworkManager keyfile in /etc/NetworkManager/system-connections
(root only, mode 600) followed by ``nmcli connection reload``. The new network is
added with a higher autoconnect priority; the known ones are kept.
``AUTO_UPDATE`` enables or disables the ``naneos_uploader_update.timer`` (see
``uploader_update.py``) with systemctl.

The installer writes the ``naneos_uploader_settings.service`` unit that runs
``naneos-uploader-settings`` as root before the uploader starts. All lines are
validated before anything is applied: a rejected file keeps the previous
settings, so the service always comes up.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from naneos import __version__
from naneos.ble import PartectorBleManager
from naneos.cli import parse_args as parse_uploader_args
from naneos.uploader_update import UPDATE_TIMER

CHANGE_FILE = "naneos-uploader-change.txt"
CURRENT_FILE = "naneos-uploader-current.txt"
ENV_KEY = "NANEOS_UPLOADER_OPTIONS"
KEYS = ("OPTIONS", "WIFI_SSID", "WIFI_PASSWORD", "AUTO_UPDATE")
_ON = ("on", "yes", "true", "1")
_OFF = ("off", "no", "false", "0")
DEFAULT_BOOT_DIR = Path("/boot/firmware")
DEFAULT_ENV_FILE = Path("/etc/naneos-uploader/options.env")
DEFAULT_OVERRIDE_DIR = Path("/etc/systemd/system/naneos_uploader.service.d")
DEFAULT_NM_DIR = Path("/etc/NetworkManager/system-connections")

_SETTING_LINE = re.compile(r"^\s*(?P<key>[A-Za-z_]+)\s*=(?P<value>.*)$")
# Everything the uploader's options need. Anything else (quotes, backslashes,
# shell characters) is refused before it reaches the environment file.
_ALLOWED_OPTIONS = re.compile(r"^[A-Za-z0-9_.,= -]*$")
# WPA passphrase: 8-63 printable ASCII characters.
_ALLOWED_PASSWORD = re.compile(r"^[\x20-\x7e]{8,63}$")


class SettingsError(ValueError):
    """The change file holds something that cannot be applied."""


def template() -> str:
    return f"""\
# naneos uploader: change the settings
#
# 1. Remove the # in front of a line below and write the value after the = sign.
# 2. Put the card back into the Raspberry Pi and switch it on.
# The settings are applied at boot. This file is then reset to this text and
# {CURRENT_FILE} shows what the service runs with.
#
# OPTIONS: the options of the naneos-uploader command, exactly as on the
# command line. "OPTIONS=" with nothing after the = restores the defaults.
#   --interval N          gathering interval in seconds (10-600), default 30
#   --no-serial           do not use USB devices
#   --no-ble              do not use Bluetooth devices
#   --no-upload           gather only, never upload
#   --ble-allow SN,SN     only link to these serial numbers over Bluetooth,
#                         default: any Partector in reach
#   --ble-max-links N     maximum number of simultaneous Bluetooth links,
#                         default {PartectorBleManager.DEFAULT_MAX_LINKS}
#   --diagnostics-interval HOURS
#                         read and upload the UI curve and pulse form of every
#                         device this often, 0.5 to 24, 0 for never, default 1
#   --upload-buffer-mb MB
#                         RAM that keeps the data while the internet is down
#                         (1-1000), default 100: about 4 days for a P2 and a
#                         P2 Pro. The oldest data goes first when it is full,
#                         and all of it is lost when the Pi restarts.
#   --log-level LEVEL     DEBUG, INFO, WARNING or ERROR, default INFO
# Example:
# OPTIONS=--interval 60 --ble-allow 8617,8764 --ble-max-links 2
#
#OPTIONS=
#
# WIFI: to add a WiFi network, fill in both lines (WPA2/WPA3 personal, the
# password has 8 to 63 characters). The network is added to the ones the Pi
# already knows, nothing is removed, and it is preferred from then on.
# The password is removed from this file at boot.
#
#WIFI_SSID=
#WIFI_PASSWORD=
#
# AUTO_UPDATE: on = once a day, install a new release of the naneos software
# if there is one (the service restarts once for it). off = never (default).
#
#AUTO_UPDATE=
"""


def read_settings(text: str) -> dict[str, str]:
    """The settings lines as {KEY: value}; comments and blank lines are skipped.

    Raises SettingsError for an unknown key, a repeated key or any other content.
    Error messages never echo a value, since they end up in a world-readable file.
    """
    found: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _SETTING_LINE.match(line)
        if match is None:
            raise SettingsError(f"line {number} is not a KEY=value line")
        key = match.group("key").upper()
        if key not in KEYS:
            raise SettingsError(f"line {number}: unknown setting {key}, allowed: {', '.join(KEYS)}")
        if key in found:
            raise SettingsError(f"line {number}: {key} is given twice")
        value = match.group("value").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].strip()
        found[key] = value
    return found


def validate_options(options: str) -> str:
    """The options normalized to single spaces, after the uploader's parser accepted them."""
    if not _ALLOWED_OPTIONS.match(options):
        raise SettingsError(f"unexpected character in OPTIONS: {options}")
    argv = options.split()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            parse_uploader_args(argv)
    except SystemExit as e:
        if e.code == 0:
            raise SettingsError("OPTIONS: --help and --version are not settings") from None
        lines = [line for line in stderr.getvalue().splitlines() if line.strip()]
        message = lines[-1] if lines else "invalid options"
        raise SettingsError("OPTIONS: " + message.split("error: ", 1)[-1]) from None
    return " ".join(argv)


def validate_wifi(settings: dict[str, str]) -> tuple[str, str] | None:
    """(ssid, password) if the file adds a network, None if both lines are absent."""
    ssid = settings.get("WIFI_SSID")
    password = settings.get("WIFI_PASSWORD")
    if ssid is None and password is None:
        return None
    if not ssid:
        raise SettingsError("WIFI_SSID is missing or empty")
    if len(ssid.encode("utf-8")) > 32:
        raise SettingsError("WIFI_SSID is longer than 32 bytes")
    if password is None:
        raise SettingsError("WIFI_PASSWORD is missing")
    if not _ALLOWED_PASSWORD.match(password):
        raise SettingsError("WIFI_PASSWORD must have 8 to 63 characters (letters, digits, symbols)")
    return ssid, password


def validate_auto_update(settings: dict[str, str]) -> bool | None:
    """True/False for AUTO_UPDATE=on/off, None if the line is absent."""
    value = settings.get("AUTO_UPDATE")
    if value is None:
        return None
    if value.lower() in _ON:
        return True
    if value.lower() in _OFF:
        return False
    raise SettingsError("AUTO_UPDATE must be on or off")


def systemctl_auto_update(enabled: bool) -> str | None:
    """Switch the update timer; a warning if systemctl could not do it."""
    action = "enable" if enabled else "disable"
    try:
        subprocess.run(
            ["systemctl", action, "--now", UPDATE_TIMER],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return "systemctl not found: automatic updates could not be switched"
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or "").strip().splitlines()
        reason = detail[-1] if detail else str(e)
        return f"could not {action} automatic updates ({reason}), re-run the installer"
    except subprocess.SubprocessError as e:
        return f"could not {action} automatic updates ({e})"
    return None


def systemctl_auto_update_state() -> bool | None:
    """Whether the update timer is enabled, None if it is not installed."""
    try:
        result = subprocess.run(
            ["systemctl", "is-enabled", UPDATE_TIMER], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    state = result.stdout.strip()
    if state in ("enabled", "enabled-runtime", "static"):
        return True
    if state in ("disabled", "masked"):
        return False
    return None


def read_env(env_file: Path) -> str:
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == ENV_KEY:
            return value.strip()
    return ""


def write_env(env_file: Path, options: str) -> None:
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text(f"{ENV_KEY}={options}\n", encoding="utf-8")


def _keyfile_value(text: str) -> str:
    """Escape a value for a GKeyFile line (NetworkManager's keyfile format)."""
    text = text.replace("\\", "\\\\")
    if text.startswith(" "):
        text = "\\s" + text[1:]
    return text


def wifi_keyfile(ssid: str, password: str) -> str:
    # The SSID as a byte list: that form takes any character and is what
    # NetworkManager itself writes for non-ASCII names.
    ssid_bytes = "".join(f"{b};" for b in ssid.encode("utf-8"))
    return f"""\
[connection]
id={_keyfile_value(ssid)}
uuid={uuid.uuid4()}
type=wifi
autoconnect=true
autoconnect-priority=10

[wifi]
mode=infrastructure
ssid={ssid_bytes}

[wifi-security]
key-mgmt=wpa-psk
psk={_keyfile_value(password)}

[ipv4]
method=auto

[ipv6]
method=auto
addr-gen-mode=default
"""


def wifi_profile_path(nm_dir: Path, ssid: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", ssid).strip("_") or "wifi"
    return nm_dir / f"naneos-{slug}.nmconnection"


def write_wifi_profile(nm_dir: Path, ssid: str, password: str) -> Path:
    """Write the keyfile root-only (NetworkManager ignores it otherwise)."""
    nm_dir.mkdir(parents=True, exist_ok=True)
    path = wifi_profile_path(nm_dir, ssid)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(wifi_keyfile(ssid, password))
    os.chmod(path, 0o600)
    return path


def nmcli_reload() -> str | None:
    """Tell a running NetworkManager about the new profile; a warning if that was not possible."""
    if shutil.which("nmcli") is None:
        return "nmcli not found: the WiFi profile is picked up at the next boot"
    try:
        subprocess.run(
            ["nmcli", "connection", "reload"], check=True, capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as e:
        return (
            f"nmcli connection reload failed ({e}): the WiFi profile is picked up at the next boot"
        )
    return None


def known_wifi(nm_dir: Path) -> list[str]:
    """The ids of the WiFi profiles NetworkManager has (needs root to read)."""
    names: list[str] = []
    if not nm_dir.is_dir():
        return names
    for path in sorted(nm_dir.glob("*.nmconnection")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not re.search(r"^type=(wifi|802-11-wireless)$", text, re.MULTILINE):
            continue
        match = re.search(r"^id=(.*)$", text, re.MULTILINE)
        names.append(match.group(1) if match else path.stem)
    return names


def override_warning(override_dir: Path) -> str | None:
    """A note if a `systemctl edit` drop-in replaces ExecStart, since that wins over the file."""
    if not override_dir.is_dir():
        return None
    for conf in sorted(override_dir.glob("*.conf")):
        with contextlib.suppress(OSError):
            for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().startswith("ExecStart=") and line.strip() != "ExecStart=":
                    return f"{conf} replaces the command, the options above are not in effect"
    return None


@dataclass
class Result:
    current: str
    applied: str | None = None
    wifi: str | None = None
    auto_update: bool | None = None
    auto_update_state: bool | None = None
    error: str | None = None
    rejected: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    known_wifi: list[str] = field(default_factory=list)

    def describe(self) -> str:
        if self.error is not None:
            return f"rejected ({self.error}), still running with {self.current!r}"
        parts = []
        if self.applied is not None:
            parts.append(f"applied {self.applied!r}")
        if self.wifi is not None:
            parts.append(f"added WiFi {self.wifi!r}")
        if self.auto_update is not None:
            parts.append(f"automatic updates {'on' if self.auto_update else 'off'}")
        return ", ".join(parts) or f"unchanged, running with {self.current!r}"


def apply(
    boot_dir: Path,
    env_file: Path,
    override_dir: Path = DEFAULT_OVERRIDE_DIR,
    nm_dir: Path = DEFAULT_NM_DIR,
    nm_reload: Callable[[], str | None] = nmcli_reload,
    set_auto_update: Callable[[bool], str | None] = systemctl_auto_update,
    auto_update_state: Callable[[], bool | None] = systemctl_auto_update_state,
    now: datetime | None = None,
) -> Result:
    """One boot: consume the change file, apply what it holds, write the current file."""
    change_file = boot_dir / CHANGE_FILE
    result = Result(current=read_env(env_file))

    if not change_file.exists():
        change_file.write_text(template(), encoding="utf-8")
    else:
        _consume_change_file(change_file, env_file, nm_dir, nm_reload, set_auto_update, result)

    warning = override_warning(override_dir)
    if warning is not None:
        result.warnings.append(warning)
    result.known_wifi = known_wifi(nm_dir)
    result.auto_update_state = auto_update_state()
    (boot_dir / CURRENT_FILE).write_text(_current_text(result, now), encoding="utf-8")
    return result


def _consume_change_file(
    change_file: Path,
    env_file: Path,
    nm_dir: Path,
    nm_reload: Callable[[], str | None],
    set_auto_update: Callable[[bool], str | None],
    result: Result,
) -> None:
    """Validate and apply the change file, then reset it.

    A change that cannot be applied is recorded in result.error and in the file
    (which is reset too, so a WiFi password never stays on the card).
    """
    # utf-8-sig drops the BOM Notepad may add; splitlines handles CRLF.
    text = change_file.read_text(encoding="utf-8-sig", errors="replace")
    try:
        settings = read_settings(text)
        result.rejected = [
            f"{key}={'****' if key == 'WIFI_PASSWORD' else value}"
            for key, value in settings.items()
        ]
        # Validate everything first: a bad line applies nothing.
        options = settings.get("OPTIONS")
        validated = validate_options(options) if options is not None else None
        wifi = validate_wifi(settings)
        auto_update = validate_auto_update(settings)

        _write_settings(
            validated, wifi, auto_update, env_file, nm_dir, nm_reload, set_auto_update, result
        )

        result.rejected = []
        if validated is not None or wifi is not None or auto_update is not None:
            change_file.write_text(template(), encoding="utf-8")
    except SettingsError as e:
        result.error = str(e)
        change_file.write_text(_with_error(template(), result), encoding="utf-8")


def _write_settings(
    options: str | None,
    wifi: tuple[str, str] | None,
    auto_update: bool | None,
    env_file: Path,
    nm_dir: Path,
    nm_reload: Callable[[], str | None],
    set_auto_update: Callable[[bool], str | None],
    result: Result,
) -> None:
    """Write what the validated change holds, in the order options, WiFi, updates.

    Raises SettingsError if a file cannot be written. What was applied before
    stays applied and stays in result: there is no undoing a written file.
    """
    try:
        if options is not None:
            write_env(env_file, options)
            result.current = result.applied = options
        if wifi is not None:
            write_wifi_profile(nm_dir, *wifi)
            result.wifi = wifi[0]
            warning = nm_reload()
            if warning is not None:
                result.warnings.append(warning)
    except OSError as e:
        done = ", the options were applied" if result.applied is not None else ""
        raise SettingsError(
            f"could not write the settings ({e.strerror or type(e).__name__}){done}"
        ) from e

    if auto_update is not None:
        warning = set_auto_update(auto_update)
        if warning is None:
            result.auto_update = auto_update
        else:
            result.warnings.append(warning)


def _error_lines(result: Result) -> list[str]:
    lines = [f"# !! {result.error}"]
    lines += [f"# !! rejected: {line}" for line in result.rejected]
    return lines


def _with_error(text: str, result: Result) -> str:
    return "\n".join(
        [
            "# !! The settings from the last boot were NOT applied:",
            *_error_lines(result),
            "# !! The previous settings are still in use. Fix the line and try again.",
            "#",
            text,
        ]
    )


def _state_text(state: bool | None) -> str:
    if state is None:
        return "not installed (re-run the installer)"
    return "on" if state else "off"


def _current_text(result: Result, now: datetime | None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    command = Path(sys.executable).with_name("naneos-uploader")
    lines = [
        "# naneos uploader: current settings (written at every boot, editing has no effect)",
        f"# To change them, edit {CHANGE_FILE} on this card.",
        f"# naneos-devices {__version__}, written {stamp}",
        f"OPTIONS={result.current}",
        f"# command: {command} {result.current}".rstrip(),
        f"# wifi networks: {', '.join(result.known_wifi) or 'none'}",
        f"# automatic updates: {_state_text(result.auto_update_state)}",
    ]
    if result.wifi is not None:
        lines.append(f"# wifi added at this boot: {result.wifi}")
    if result.error is not None:
        lines += ["#", "# !! The last change was NOT applied:", *_error_lines(result)]
    for warning in result.warnings:
        lines += ["#", f"# !! {warning}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="naneos-uploader-settings",
        description=f"Apply {CHANGE_FILE} from the SD card to the naneos_uploader service.",
    )
    parser.add_argument("--version", action="version", version=f"naneos-devices {__version__}")
    parser.add_argument(
        "--boot-dir",
        type=Path,
        default=DEFAULT_BOOT_DIR,
        help="the boot partition with the change and current files (default: %(default)s)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="environment file the service reads (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    result = apply(args.boot_dir, args.env_file)
    print(f"{CHANGE_FILE}: {result.describe()}")
    for warning in result.warnings:
        print(f"warning: {warning}")


if __name__ == "__main__":
    main()

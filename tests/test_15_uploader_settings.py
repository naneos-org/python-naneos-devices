"""Hardware-free tests for the settings files on the SD card (naneos-uploader-settings)."""

import contextlib
import io
import re
import stat
from datetime import UTC, datetime
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from naneos.cli import parse_args as parse_uploader_args
from naneos.uploader_settings import (
    CHANGE_FILE,
    CURRENT_FILE,
    ENV_KEY,
    SettingsError,
    apply,
    main,
    read_settings,
    template,
    validate_options,
    wifi_profile_path,
)

NOW = datetime(2026, 9, 21, 14, 3, tzinfo=UTC)


@pytest.fixture
def boot(tmp_path: Path) -> Path:
    (tmp_path / "boot").mkdir()
    return tmp_path / "boot"


@pytest.fixture
def env_file(tmp_path: Path) -> Path:
    return tmp_path / "etc" / "options.env"


@pytest.fixture
def nm_dir(tmp_path: Path) -> Path:
    return tmp_path / "nm"


class FakeReload:
    def __init__(self, warning: str | None = None) -> None:
        self.calls = 0
        self.warning = warning

    def __call__(self) -> str | None:
        self.calls += 1
        return self.warning


class FakeTimer:
    """Stands in for systemctl enable/disable and is-enabled of the update timer."""

    def __init__(self, state: bool | None = False, warning: str | None = None) -> None:
        self.state = state
        self.warning = warning
        self.calls: list[bool] = []

    def switch(self, enabled: bool) -> str | None:
        self.calls.append(enabled)
        if self.warning is None:
            self.state = enabled
        return self.warning

    def is_enabled(self) -> bool | None:
        return self.state


def run(
    boot: Path,
    env_file: Path,
    nm_dir: Path,
    reload: FakeReload | None = None,
    timer: FakeTimer | None = None,
):
    timer = timer or FakeTimer()
    return apply(
        boot,
        env_file,
        override_dir=boot / "none",
        nm_dir=nm_dir,
        nm_reload=reload or FakeReload(),
        set_auto_update=timer.switch,
        auto_update_state=timer.is_enabled,
        now=NOW,
    )


def test_console_script_is_registered() -> None:
    scripts = {ep.name: ep.value for ep in entry_points(group="console_scripts")}
    assert scripts.get("naneos-uploader-settings") == "naneos.uploader_settings:main"


def test_template_has_no_active_line_and_lists_the_settings() -> None:
    text = template()
    assert read_settings(text) == {}
    for option in ["--interval", "--no-serial", "--no-ble", "--no-upload", "--ble-allow"]:
        assert option in text
    assert "--ble-max-links N" in text and "default 7" in text
    assert "--no-ble-p2pro-mode" in text
    assert "#WIFI_SSID=" in text and "#WIFI_PASSWORD=" in text
    assert "#AUTO_UPDATE=" in text


def test_first_boot_creates_both_files_with_defaults(
    boot: Path, env_file: Path, nm_dir: Path
) -> None:
    result = run(boot, env_file, nm_dir)

    assert result.applied is None and result.error is None and result.current == ""
    assert (boot / CHANGE_FILE).read_text() == template()
    current = (boot / CURRENT_FILE).read_text()
    assert "OPTIONS=\n" in current
    assert "written 2026-09-21 14:03 UTC" in current
    assert "# wifi networks: none" in current
    assert "# automatic updates: off" in current
    assert not env_file.exists()


def test_change_is_applied_and_the_file_reset(boot: Path, env_file: Path, nm_dir: Path) -> None:
    (boot / CHANGE_FILE).write_text("# my note\nOPTIONS=--interval 60  --ble-max-links 2\n")

    result = run(boot, env_file, nm_dir)

    assert result.applied == "--interval 60 --ble-max-links 2"
    assert env_file.read_text() == f"{ENV_KEY}=--interval 60 --ble-max-links 2\n"
    assert (boot / CHANGE_FILE).read_text() == template()
    current = (boot / CURRENT_FILE).read_text()
    assert "OPTIONS=--interval 60 --ble-max-links 2\n" in current
    assert "naneos-uploader --interval 60 --ble-max-links 2" in current
    assert "!!" not in current


def test_notepad_artifacts_are_tolerated(boot: Path, env_file: Path, nm_dir: Path) -> None:
    text = '﻿# note\r\nOptions = "--ble-allow 8617,8764"\r\n'
    (boot / CHANGE_FILE).write_bytes(text.encode("utf-8"))

    assert run(boot, env_file, nm_dir).applied == "--ble-allow 8617,8764"


def test_empty_options_line_restores_the_defaults(boot: Path, env_file: Path, nm_dir: Path) -> None:
    env_file.parent.mkdir()
    env_file.write_text(f"{ENV_KEY}=--interval 60\n")
    (boot / CHANGE_FILE).write_text("OPTIONS=\n")

    result = run(boot, env_file, nm_dir)

    assert result.applied == "" and result.current == ""
    assert env_file.read_text() == f"{ENV_KEY}=\n"


def test_untouched_template_keeps_the_previous_options(
    boot: Path, env_file: Path, nm_dir: Path
) -> None:
    env_file.parent.mkdir()
    env_file.write_text(f"{ENV_KEY}=--interval 60\n")
    edited = template() + "# a comment the customer added\n"
    (boot / CHANGE_FILE).write_text(edited)

    result = run(boot, env_file, nm_dir)

    assert result.applied is None and result.current == "--interval 60"
    assert (boot / CHANGE_FILE).read_text() == edited
    assert "OPTIONS=--interval 60\n" in (boot / CURRENT_FILE).read_text()


@pytest.mark.parametrize(
    "line, message",
    [
        ("OPTIONS=--interval abc", "invalid int value"),
        ("OPTIONS=--intervall 60", "unrecognized arguments"),
        ("OPTIONS=--ble-allow 8617;rm", "unexpected character"),
        ("OPTIONS=--help", "not settings"),
        ("interval=60", "unknown setting INTERVAL"),
        ("just text", "not a KEY=value line"),
        ("OPTIONS=--no-ble\nOPTIONS=--no-serial", "OPTIONS is given twice"),
        ("WIFI_SSID=Office", "WIFI_PASSWORD is missing"),
        ("WIFI_PASSWORD=longenough", "WIFI_SSID is missing"),
        ("WIFI_SSID=Office\nWIFI_PASSWORD=short", "8 to 63 characters"),
        ("WIFI_SSID=Office\nWIFI_PASSWORD=" + "x" * 64, "8 to 63 characters"),
        ("WIFI_SSID=" + "s" * 33 + "\nWIFI_PASSWORD=longenough", "longer than 32 bytes"),
        ("AUTO_UPDATE=maybe", "AUTO_UPDATE must be on or off"),
    ],
)
def test_rejected_change_keeps_previous_options_and_explains(
    boot: Path, env_file: Path, nm_dir: Path, line: str, message: str
) -> None:
    env_file.parent.mkdir()
    env_file.write_text(f"{ENV_KEY}=--interval 60\n")
    (boot / CHANGE_FILE).write_text(line + "\n")

    result = run(boot, env_file, nm_dir)

    assert result.applied is None and result.wifi is None and result.error is not None
    assert message in result.error
    assert result.current == "--interval 60"
    assert env_file.read_text() == f"{ENV_KEY}=--interval 60\n"
    assert not nm_dir.exists()
    change = (boot / CHANGE_FILE).read_text()
    assert change.startswith("# !! The settings from the last boot were NOT applied:")
    assert message in change
    assert change.endswith(template())
    current = (boot / CURRENT_FILE).read_text()
    assert "OPTIONS=--interval 60\n" in current and message in current


def test_rejected_file_never_echoes_the_password(boot: Path, env_file: Path, nm_dir: Path) -> None:
    (boot / CHANGE_FILE).write_text(
        "OPTIONS=--interval abc\nWIFI_SSID=Office\nWIFI_PASSWORD=s3cretpass\n"
    )
    run(boot, env_file, nm_dir)
    for name in (CHANGE_FILE, CURRENT_FILE):
        text = (boot / name).read_text()
        assert "s3cretpass" not in text
        assert "# !! rejected: WIFI_PASSWORD=****" in text
        assert "# !! rejected: OPTIONS=--interval abc" in text

    # A typo in the key must not leak the value either.
    (boot / CHANGE_FILE).write_text("WIFI_PASWORD=s3cretpass\n")
    result = run(boot, env_file, nm_dir)
    assert "unknown setting WIFI_PASWORD" in str(result.error)
    for name in (CHANGE_FILE, CURRENT_FILE):
        assert "s3cretpass" not in (boot / name).read_text()


def test_wifi_is_written_as_root_only_keyfile_and_reloaded(
    boot: Path, env_file: Path, nm_dir: Path
) -> None:
    (boot / CHANGE_FILE).write_text("WIFI_SSID=Café Wifi\nWIFI_PASSWORD=pa\\ss #1=;\r\n")
    reload = FakeReload()

    result = run(boot, env_file, nm_dir, reload)

    assert result.wifi == "Café Wifi" and result.applied is None and result.error is None
    assert reload.calls == 1
    path = wifi_profile_path(nm_dir, "Café Wifi")
    assert path.name == "naneos-Caf_Wifi.nmconnection"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    keyfile = path.read_text()
    assert "type=wifi\n" in keyfile and "autoconnect-priority=10\n" in keyfile
    assert "id=Café Wifi\n" in keyfile
    ssid_bytes = "".join(f"{b};" for b in "Café Wifi".encode())
    assert f"ssid={ssid_bytes}\n" in keyfile
    assert "key-mgmt=wpa-psk\npsk=pa\\\\ss #1=;\n" in keyfile
    assert (boot / CHANGE_FILE).read_text() == template()
    current = (boot / CURRENT_FILE).read_text()
    assert "# wifi networks: Café Wifi" in current
    assert "# wifi added at this boot: Café Wifi" in current
    assert "pa\\ss" not in current


def test_options_and_wifi_apply_together(boot: Path, env_file: Path, nm_dir: Path) -> None:
    (boot / CHANGE_FILE).write_text(
        "OPTIONS=--no-ble\nWIFI_SSID=Office\nWIFI_PASSWORD=longenough\n"
    )

    result = run(boot, env_file, nm_dir)

    assert result.applied == "--no-ble" and result.wifi == "Office"
    assert env_file.read_text() == f"{ENV_KEY}=--no-ble\n"
    assert wifi_profile_path(nm_dir, "Office").exists()
    assert "applied '--no-ble', added WiFi 'Office'" == result.describe()


def test_reload_warning_is_reported_but_profile_kept(
    boot: Path, env_file: Path, nm_dir: Path
) -> None:
    (boot / CHANGE_FILE).write_text("WIFI_SSID=Office\nWIFI_PASSWORD=longenough\n")

    result = run(
        boot,
        env_file,
        nm_dir,
        FakeReload("nmcli not found: the WiFi profile is picked up at the next boot"),
    )

    assert result.wifi == "Office"
    assert wifi_profile_path(nm_dir, "Office").exists()
    assert any("nmcli not found" in w for w in result.warnings)
    assert "# !! nmcli not found" in (boot / CURRENT_FILE).read_text()


def test_known_wifi_lists_existing_profiles(boot: Path, env_file: Path, nm_dir: Path) -> None:
    nm_dir.mkdir()
    (nm_dir / "preconfigured.nmconnection").write_text(
        "[connection]\nid=Home\ntype=wifi\n\n[wifi]\nssid=Home\n"
    )
    (nm_dir / "Wired connection 1.nmconnection").write_text(
        "[connection]\nid=Wired connection 1\ntype=ethernet\n"
    )

    result = run(boot, env_file, nm_dir)

    assert result.known_wifi == ["Home"]
    assert "# wifi networks: Home\n" in (boot / CURRENT_FILE).read_text()


@pytest.mark.parametrize(
    "value, enabled", [("on", True), ("Yes", True), ("off", False), ("0", False)]
)
def test_auto_update_switches_the_timer(
    boot: Path, env_file: Path, nm_dir: Path, value: str, enabled: bool
) -> None:
    (boot / CHANGE_FILE).write_text(f"AUTO_UPDATE={value}\n")
    timer = FakeTimer(state=not enabled)

    result = run(boot, env_file, nm_dir, timer=timer)

    assert timer.calls == [enabled]
    assert result.auto_update is enabled and result.error is None
    assert (boot / CHANGE_FILE).read_text() == template()
    current = (boot / CURRENT_FILE).read_text()
    assert f"# automatic updates: {'on' if enabled else 'off'}" in current
    assert result.describe() == f"automatic updates {'on' if enabled else 'off'}"


def test_auto_update_without_timer_installed_is_a_warning(
    boot: Path, env_file: Path, nm_dir: Path
) -> None:
    (boot / CHANGE_FILE).write_text("AUTO_UPDATE=on\n")
    timer = FakeTimer(
        state=None, warning="could not enable automatic updates (x), re-run the installer"
    )

    result = run(boot, env_file, nm_dir, timer=timer)

    assert result.auto_update is None and result.error is None
    assert any("re-run the installer" in w for w in result.warnings)
    current = (boot / CURRENT_FILE).read_text()
    assert "# automatic updates: not installed" in current
    assert "# !! could not enable automatic updates" in current


def test_rejected_file_switches_nothing(boot: Path, env_file: Path, nm_dir: Path) -> None:
    (boot / CHANGE_FILE).write_text("AUTO_UPDATE=on\nOPTIONS=--interval abc\n")
    timer = FakeTimer()

    result = run(boot, env_file, nm_dir, timer=timer)

    assert result.error is not None and timer.calls == []


def test_validate_options_normalizes_whitespace() -> None:
    assert validate_options("  --no-ble   --interval  10 ") == "--no-ble --interval 10"
    with pytest.raises(SettingsError):
        validate_options("--interval")


def test_validate_options_refuses_a_diagnostics_interval_that_would_stop_the_service() -> None:
    assert validate_options("--diagnostics-interval 0") == "--diagnostics-interval 0"
    assert validate_options("--diagnostics-interval 0.5") == "--diagnostics-interval 0.5"
    with pytest.raises(SettingsError, match="diagnostics-interval"):
        validate_options("--diagnostics-interval -1")


def test_systemctl_override_is_reported(boot: Path, env_file: Path, nm_dir: Path) -> None:
    override_dir = boot / "override.d"
    override_dir.mkdir()
    (override_dir / "override.conf").write_text(
        "[Service]\nExecStart=\nExecStart=/x/naneos-uploader --no-ble\n"
    )

    timer = FakeTimer()
    result = apply(
        boot,
        env_file,
        override_dir=override_dir,
        nm_dir=nm_dir,
        nm_reload=FakeReload(),
        set_auto_update=timer.switch,
        auto_update_state=timer.is_enabled,
    )

    assert any("override.conf" in w for w in result.warnings)
    assert "replaces the command" in (boot / CURRENT_FILE).read_text()


def test_main_prints_the_outcome(boot: Path, env_file: Path, capsys: pytest.CaptureFixture) -> None:
    (boot / CHANGE_FILE).write_text("OPTIONS=--no-upload\n")

    main(["--boot-dir", str(boot), "--env-file", str(env_file)])

    assert f"{CHANGE_FILE}: applied '--no-upload'" in capsys.readouterr().out


def test_a_wifi_profile_that_cannot_be_written_is_reported_and_the_password_leaves_the_card(
    boot: Path, env_file: Path, tmp_path: Path
) -> None:
    nm_file = tmp_path / "nm"
    nm_file.write_text("not a directory")  # the profile cannot be created below it
    (boot / CHANGE_FILE).write_text(
        "OPTIONS=--interval 60\nWIFI_SSID=Lab\nWIFI_PASSWORD=hunter2hunter2\n"
    )

    result = run(boot, env_file, nm_file)  # must not raise: the installer runs this with set -e

    assert result.error is not None
    assert "could not write the settings" in result.error
    assert "the options were applied" in result.error
    assert env_file.read_text() == f"{ENV_KEY}=--interval 60\n"  # what was written stays
    assert result.current == "--interval 60"
    for name in (CHANGE_FILE, CURRENT_FILE):
        text = (boot / name).read_text()
        assert "hunter2hunter2" not in text
        assert "could not write the settings" in text
    assert "WIFI_PASSWORD=****" in (boot / CHANGE_FILE).read_text()


def test_options_that_cannot_be_written_are_reported_without_claiming_they_were_applied(
    boot: Path, tmp_path: Path, nm_dir: Path
) -> None:
    (tmp_path / "etc").write_text("not a directory")  # the environment file cannot go below it
    (boot / CHANGE_FILE).write_text("OPTIONS=--interval 60\n")

    result = run(boot, tmp_path / "etc" / "options.env", nm_dir)

    assert result.error is not None
    assert "could not write the settings" in result.error
    assert "were applied" not in result.error
    assert result.applied is None and result.current == ""
    assert "!!" in (boot / CURRENT_FILE).read_text()


def test_the_template_describes_every_option_of_the_uploader_and_nothing_else() -> None:
    help_text = io.StringIO()
    with contextlib.redirect_stdout(help_text), pytest.raises(SystemExit):
        parse_uploader_args(["--help"])
    in_cli = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", help_text.getvalue()))
    in_cli -= {"--help", "--version"}  # not settings, see validate_options()

    described = set(re.findall(r"^#   (--[a-z][a-z-]*)", template(), re.MULTILINE))

    assert described == in_cli, "a new uploader option needs a line in template()"


def test_the_upload_buffer_is_a_setting_between_1_and_1000_mb() -> None:
    assert parse_uploader_args([]).upload_buffer_mb == 100
    assert parse_uploader_args(["--upload-buffer-mb", "1"]).upload_buffer_mb == 1
    assert parse_uploader_args(["--upload-buffer-mb", "250.5"]).upload_buffer_mb == 250.5
    assert validate_options("--upload-buffer-mb 50") == "--upload-buffer-mb 50"

    for bad in ("0", "0.5", "-5", "1001", "100000", "nan", "inf", "lots"):
        with pytest.raises(SettingsError, match="upload-buffer-mb"):
            validate_options(f"--upload-buffer-mb {bad}")

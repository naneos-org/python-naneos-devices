"""Hardware-free tests for the naneos-gui command line (no Qt needed)."""

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from naneos import __version__
from naneos.gui import app
from naneos.gui.app import main, parse_args


class FakeAutostart:
    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled
        self.calls: list[str] = []

    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self.calls.append("enable")
        self._enabled = True

    def disable(self) -> None:
        self.calls.append("disable")
        self._enabled = False


def test_defaults_start_the_tray_app() -> None:
    args = parse_args([])
    assert not args.quit
    assert args.autostart is None
    assert args.integration is None
    assert not args.no_upload
    assert args.log_level == "INFO"
    assert args.timeout == 30.0


def test_version_flag(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        parse_args(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"naneos-gui {__version__}"


def test_rejects_an_unknown_autostart_value() -> None:
    with pytest.raises(SystemExit) as exit_info:
        parse_args(["--autostart", "maybe"])
    assert exit_info.value.code == 2


def test_autostart_on_and_off(monkeypatch, capsys) -> None:
    fake = FakeAutostart()
    monkeypatch.setattr(app, "get_autostart", lambda: fake)

    assert main(["--autostart", "on"]) == 0
    assert main(["--autostart", "off"]) == 0

    assert fake.calls == ["enable", "disable"]
    assert capsys.readouterr().out.splitlines() == ["Start at login: on", "Start at login: off"]


def test_autostart_status_exit_code_tells_whether_it_is_on(monkeypatch, capsys) -> None:
    monkeypatch.setattr(app, "get_autostart", lambda: FakeAutostart(enabled=True))
    assert main(["--autostart", "status"]) == 0
    monkeypatch.setattr(app, "get_autostart", lambda: FakeAutostart(enabled=False))
    assert main(["--autostart", "status"]) == 1

    assert capsys.readouterr().out.splitlines() == ["Start at login: on", "Start at login: off"]


def test_integration_install_and_remove(monkeypatch, capsys) -> None:
    calls: list[str] = []
    monkeypatch.setattr(app, "install_integration", lambda: calls.append("install") or [Path("/a")])
    monkeypatch.setattr(app, "remove_integration", lambda: calls.append("remove"))

    assert main(["--integration", "install"]) == 0
    assert main(["--integration", "remove"]) == 0

    assert calls == ["install", "remove"]
    assert "Installed /a" in capsys.readouterr().out


def test_setup_actions_do_not_start_the_tray_app(monkeypatch) -> None:
    def fail(args):
        raise AssertionError("the tray app must not start")

    monkeypatch.setattr(app, "run_tray", fail)
    monkeypatch.setattr(app, "get_autostart", lambda: FakeAutostart())
    monkeypatch.setattr(app, "install_integration", lambda: [])

    assert main(["--integration", "install", "--autostart", "on"]) == 0


def test_quit_passes_the_timeout_on(monkeypatch) -> None:
    seen: list[float] = []
    monkeypatch.setattr(app, "_quit_running", lambda timeout: seen.append(timeout) or 2)

    assert main(["--quit", "--timeout", "7"]) == 2
    assert seen == [7.0]


def test_a_plain_start_runs_the_tray_app(monkeypatch) -> None:
    monkeypatch.setattr(app, "run_tray", lambda args: 42)
    assert main([]) == 42


def test_the_log_goes_to_a_file_in_a_log_folder_that_does_not_exist_yet(
    monkeypatch, tmp_path
) -> None:
    folder = tmp_path / "Library" / "Logs" / "naneos-devices"
    monkeypatch.setattr(app, "log_dir", lambda: folder)
    root = logging.getLogger("naneos")
    before = list(root.handlers)
    try:
        app._setup_logging(logging.INFO)
        app.logger.info("first line")
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                handler.close()
                root.removeHandler(handler)

    assert folder.is_dir()  # not a file named like the folder
    assert "first line" in (folder / "naneos-devices.log").read_text()


def _imports_in_a_fresh_interpreter(
    code: str, home: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run code in a new interpreter; `home` keeps what it writes (the log) out of the real one."""
    env = dict(os.environ)
    if home is not None:
        env.update(
            HOME=str(home),
            USERPROFILE=str(home),
            LOCALAPPDATA=str(home / "local"),
            XDG_STATE_HOME=str(home / "state"),
        )
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, env=env
    )


def test_the_uploader_never_imports_the_gui_or_qt() -> None:
    """The Raspberry Pi installs naneos-devices without the gui extra."""
    result = _imports_in_a_fresh_interpreter(
        "import sys\n"
        "import naneos, naneos.cli, naneos.manager\n"
        "import naneos.uploader_settings, naneos.uploader_update\n"
        "loaded = [m for m in sys.modules if m == 'PySide6' or m.startswith('naneos.gui')]\n"
        "assert not loaded, loaded\n"
    )
    assert result.returncode == 0, result.stderr


def test_the_command_line_parts_of_the_gui_work_without_qt() -> None:
    """--version, --autostart and --integration must not need PySide6 (the installers use them)."""
    result = _imports_in_a_fresh_interpreter(
        "import sys\n"
        "import naneos.gui.app, naneos.gui.model, naneos.gui.integration\n"
        "assert 'PySide6' not in sys.modules\n"
    )
    assert result.returncode == 0, result.stderr


def test_a_missing_qt_gets_a_hint_instead_of_a_traceback(tmp_path) -> None:
    result = _imports_in_a_fresh_interpreter(
        "import sys\n"
        "sys.modules['PySide6'] = None  # makes every import of it fail\n"
        "from naneos.gui.app import main\n"
        "sys.exit(main(['--no-upload']))\n",
        home=tmp_path,
    )
    assert result.returncode == 1
    assert "naneos-devices[gui]" in result.stderr
    assert "Traceback" not in result.stderr

"""Hardware-free tests for the naneos-uploader command."""

from importlib.metadata import entry_points

import pytest

from naneos import cli
from naneos.cli import parse_args


def test_console_script_is_registered() -> None:
    scripts = {ep.name: ep.value for ep in entry_points(group="console_scripts")}
    assert scripts.get("naneos-uploader") == "naneos.cli:main"


def test_defaults_match_the_service_configuration() -> None:
    args = parse_args([])
    assert (args.interval, args.no_serial, args.no_ble, args.no_upload) == (30, False, False, False)
    assert args.log_level == "INFO"


def test_test_run_flags() -> None:
    args = parse_args(["--no-upload", "--no-ble", "--interval", "10", "--log-level", "DEBUG"])
    assert args.no_upload and args.no_ble and not args.no_serial
    assert args.interval == 10
    assert args.log_level == "DEBUG"


def test_ble_allow_list_and_link_cap() -> None:
    args = parse_args([])
    assert args.ble_allow is None
    assert args.ble_max_links == 7

    args = parse_args(["--ble-allow", "8617,8764", "--ble-max-links", "3"])
    assert args.ble_allow == [8617, 8764]
    assert args.ble_max_links == 3


def test_the_ble_mode_switch_is_on_unless_switched_off() -> None:
    assert parse_args([]).no_ble_p2pro_mode is False
    assert parse_args(["--no-ble-p2pro-mode"]).no_ble_p2pro_mode is True


def test_run_hands_the_ble_mode_switch_to_the_manager(monkeypatch) -> None:
    made: dict = {}

    class FakeManager:
        def __init__(self, **kwargs) -> None:
            made.update(kwargs)

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def join(self) -> None:
            pass

    def leave_the_loop(seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "NaneosDeviceManager", FakeManager)
    monkeypatch.setattr(cli.signal, "signal", lambda *args: None)  # not the handlers of pytest
    monkeypatch.setattr(cli, "enable_console_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.time, "sleep", leave_the_loop)

    for flags, expected in (([], True), (["--no-ble-p2pro-mode"], False)):
        with pytest.raises(KeyboardInterrupt):
            cli.run(parse_args(flags))
        assert made["ble_p2pro_mode"] is expected


def test_installed_from_names_a_source() -> None:
    from naneos.cli import installed_from

    source = installed_from()
    assert isinstance(source, str) and source

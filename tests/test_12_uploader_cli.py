"""Hardware-free tests for the naneos-uploader command."""

from importlib.metadata import entry_points

from naneos.uploader import parse_args


def test_console_script_is_registered() -> None:
    scripts = {ep.name: ep.value for ep in entry_points(group="console_scripts")}
    assert scripts.get("naneos-uploader") == "naneos.uploader:main"


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

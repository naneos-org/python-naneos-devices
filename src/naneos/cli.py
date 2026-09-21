"""The `naneos-uploader` command: gather from every device in reach and upload.

This is what the Raspberry Pi service runs (see installers/install.sh). It
can also be started by hand, for example to test a Pi without uploading:

    naneos-uploader --no-upload --interval 10
"""

import argparse
import json
import logging
import shutil
import signal
import subprocess
import time
from importlib.metadata import PackageNotFoundError, distribution
from typing import Any

from naneos import __version__
from naneos.ble import PartectorBleManager
from naneos.logger import enable_console_logging, get_naneos_logger
from naneos.manager import NaneosDeviceManager

logger = get_naneos_logger("naneos.cli")


def warn_if_wifi_power_save_on() -> None:
    """Log a warning if the WiFi chip is allowed to sleep.

    Turning it off needs root and outlives the process, so the installer does
    that. This service runs as an unprivileged user and can only report it: on a
    Pi Zero 2 W power save parks the link when idle, which stalls uploads and
    costs BLE airtime on the antenna the two radios share.
    """
    if shutil.which("iw") is None:
        return

    try:
        result = subprocess.run(["iw", "dev"], capture_output=True, text=True, timeout=5)
        devices = [
            line.split()[1]
            for line in result.stdout.splitlines()
            if line.strip().startswith("Interface")
        ]

        for device in devices:
            result = subprocess.run(
                ["iw", "dev", device, "get", "power_save"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "on" in result.stdout.split():
                logger.warning(
                    f"WiFi power save is on for {device}: uploads may stall, and BLE "
                    f"shares the antenna. Run `sudo iw dev {device} set power_save off`, "
                    "or re-run the installer to make it persistent."
                )
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"Could not read WiFi power save state: {e}")


def _serial_list(text: str) -> list[int]:
    try:
        return [int(part) for part in text.split(",") if part.strip()]
    except ValueError as e:
        raise argparse.ArgumentTypeError("expected serial numbers like 8617,8764") from e


def installed_from() -> str:
    """Where pip got the package from (a git archive URL, a path) or "PyPI".

    Lets the first log line tell which branch or tag a Pi is running, since the
    version number alone does not.
    """
    try:
        text = distribution("naneos-devices").read_text("direct_url.json")
    except PackageNotFoundError:
        return "an uninstalled checkout"
    if not text:
        return "PyPI"
    try:
        return str(json.loads(text).get("url", "unknown source"))
    except ValueError:
        return "unknown source"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="naneos-uploader",
        description="Gather data from every Partector on USB and BLE and upload it to naneos.",
    )
    parser.add_argument("--version", action="version", version=f"naneos-devices {__version__}")
    parser.add_argument(
        "--interval", type=int, default=30, help="gathering interval in seconds (10-600)"
    )
    parser.add_argument("--no-serial", action="store_true", help="do not use USB devices")
    parser.add_argument("--no-ble", action="store_true", help="do not use Bluetooth devices")
    parser.add_argument("--no-upload", action="store_true", help="gather only, never upload")
    parser.add_argument(
        "--ble-allow",
        type=_serial_list,
        default=None,
        metavar="SN[,SN...]",
        help="only link to these serial numbers over BLE (default: any Partector in reach)",
    )
    parser.add_argument(
        "--ble-max-links",
        type=int,
        default=PartectorBleManager.DEFAULT_MAX_LINKS,
        help="maximum number of simultaneous BLE links (default: %(default)s)",
    )
    parser.add_argument(
        "--diagnostics-interval",
        type=float,
        default=1.0,
        metavar="HOURS",
        help="read and upload the UI curve and pulse form of every device this often, "
        "0 for never (default: %(default)s)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="verbosity of the log output on stderr",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> None:
    enable_console_logging(getattr(logging, args.log_level), colored=False)
    logger.info(f"naneos-uploader {__version__} starting (installed from {installed_from()})")
    warn_if_wifi_power_save_on()

    running = True

    def handle_signal(signum: int, frame: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    manager = NaneosDeviceManager(
        use_serial=not args.no_serial,
        use_ble=not args.no_ble,
        upload_active=not args.no_upload,
        gathering_interval_seconds=args.interval,
        ble_serial_numbers=args.ble_allow,
        ble_max_links=args.ble_max_links,
        diagnostics_interval_hours=args.diagnostics_interval or None,
    )
    manager.start()

    try:
        while running:
            time.sleep(1)
    finally:
        logger.info("naneos-uploader stopping")
        manager.stop()
        manager.join()


def main(argv: list[str] | None = None) -> None:
    run(parse_args(argv))


if __name__ == "__main__":
    main()

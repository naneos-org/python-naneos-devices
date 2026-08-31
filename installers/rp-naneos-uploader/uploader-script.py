import shutil
import signal
import subprocess
import time

from naneos.logger import LEVEL_INFO, get_naneos_logger
from naneos.manager import NaneosDeviceManager

logger = get_naneos_logger(__name__, LEVEL_INFO)

running = True  # global flag to control the main loop


def warn_if_wifi_power_save_on() -> None:
    """Log a warning if the WiFi chip is allowed to sleep.

    Turning it off needs root and outlives the process, so install.sh does that.
    This service runs as an unprivileged user and can only report it: on a Pi
    Zero 2 W power save parks the link when idle, which stalls uploads and costs
    BLE airtime on the antenna the two radios share.
    """
    if shutil.which("iw") is None:
        return

    try:
        result = subprocess.run(
            ["iw", "dev"], capture_output=True, text=True, timeout=5, check=False
        )
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
                check=False,
            )
            if "on" in result.stdout.split():
                logger.warning(
                    f"WiFi power save is on for {device}: uploads may stall, and BLE "
                    f"shares the antenna. Run `sudo iw dev {device} set power_save off`, "
                    "or re-run install.sh to make it persistent."
                )
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"Could not read WiFi power save state: {e}")


def handle_signal(signum, frame):
    global running
    running = False


# register signal handlers for SIGTERM and SIGINT
signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def rp_service_main() -> None:
    warn_if_wifi_power_save_on()

    manager = NaneosDeviceManager(
        use_serial=True, use_ble=True, upload_active=True, gathering_interval_seconds=30
    )
    manager.start()

    try:
        while running:
            remaining = manager.get_seconds_until_next_upload()

            slept = 0
            while running and slept < remaining + 1:
                time.sleep(1)
                slept += 1

            if not running:
                break

    finally:
        manager.stop()
        manager.join()


if __name__ == "__main__":
    rp_service_main()

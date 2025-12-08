import signal
import time

from naneos.manager import NaneosDeviceManager

running = True  # global flag to control the main loop


def handle_signal(signum, frame):
    global running
    running = False


# register signal handlers for SIGTERM and SIGINT
signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def rp_service_main() -> None:
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

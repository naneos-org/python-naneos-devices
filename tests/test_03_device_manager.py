import os
import signal
import threading
import time

import pytest

from naneos.manager import NaneosDeviceManager


def raise_keyboard_interrupt():
    os.kill(os.getpid(), signal.SIGINT)


@pytest.mark.timeout(30)
def test_naneos_device_manager():
    timer = threading.Timer(20, raise_keyboard_interrupt)  # trigger keyboard interrupt after 20s
    timer.start()

    manager = NaneosDeviceManager()
    manager.start()

    try:
        while True:
            time.sleep(1)
            print(f"Seconds until next upload: {manager.get_seconds_until_next_upload():.0f}")
            print(manager.get_connected_serial_devices())
            print(manager.get_connected_ble_devices())
            print()
    except KeyboardInterrupt:
        manager.stop()
        manager.join()
        print("NaneosDeviceManager stopped.")

    timer.cancel()

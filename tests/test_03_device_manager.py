import os
import signal
import threading
import time

import pytest

from naneos.manager import NaneosDeviceManager

pytestmark = pytest.mark.hardware  # needs a Partector on USB or BLE


def raise_keyboard_interrupt():
    os.kill(os.getpid(), signal.SIGINT)


# 20 s of running plus the shutdown: a BLE link that is inside a connect attempt to
# some other Partector in reach is only cancelled after the 8 s grace period.
@pytest.mark.timeout(45)
def test_naneos_device_manager():
    timer = threading.Timer(20, raise_keyboard_interrupt)  # trigger keyboard interrupt after 20s
    timer.start()

    manager = NaneosDeviceManager()
    manager.start()

    try:
        while True:
            time.sleep(1)
            print(f"Seconds until next upload: {manager.seconds_until_next_snapshot:.0f}")
            print(manager.get_devices())
            print()
    except KeyboardInterrupt:
        manager.stop()
        manager.join()
        print("NaneosDeviceManager stopped.")

    timer.cancel()

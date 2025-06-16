import time

from naneos.manager import NaneosDeviceManager


def test_naneos_device_manager():
    manager = NaneosDeviceManager()
    manager.start()

    time.sleep(40)  # Allow some time for the manager to start

    manager.stop()
    manager.join()

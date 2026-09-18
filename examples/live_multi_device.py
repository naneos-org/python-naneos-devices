"""Live data of several USB devices at 10 Hz: print the LDSA of every point as it arrives.

The manager connects every device at 1 Hz; the rate is raised to 10 Hz here as
soon as a device shows up (again, after a reconnect).

Usage: python live_multi_device.py        (stop with Ctrl+C)
"""

import queue
import time

from naneos import NaneosDeviceDataPoint, NaneosDeviceManager, PartectorDevice
from naneos.usb.partector import Partector2Pro

SAMPLE_RATE_HZ = 10


def set_rate(device: PartectorDevice) -> None:
    if isinstance(device, Partector2Pro):
        # A P2 Pro starts in size distribution mode, which has no selectable rate.
        device.set_size_distribution(False, SAMPLE_RATE_HZ)
    else:
        device.set_sample_rate(SAMPLE_RATE_HZ)
    print(f"SN{device.serial_number}: set to {SAMPLE_RATE_HZ} Hz")


def main() -> None:
    # Bounded: if this loop falls behind, the oldest points are dropped.
    live: queue.Queue[NaneosDeviceDataPoint] = queue.Queue(maxsize=10_000)

    manager = NaneosDeviceManager(
        use_ble=False,  # the rate can only be set on USB
        upload_active=False,
        serial_gain_test=False,  # otherwise the data is held back for 10+ s after a connect
    )
    manager.register_live_queue(live)
    manager.start()

    configured: dict[int | None, PartectorDevice] = {}  # the handle each rate was set on
    next_check = 0.0
    try:
        while True:
            if time.monotonic() >= next_check:
                next_check = time.monotonic() + 1.0
                for device in manager.get_devices():
                    if configured.get(device.serial_number) is not device:  # new or reconnected
                        set_rate(device)
                        configured[device.serial_number] = device

            try:
                point = live.get(timeout=0.2)
            except queue.Empty:
                continue
            print(f"SN{point.serial_number}: LDSA {point.ldsa:6.1f} um^2/cm^3")
    except KeyboardInterrupt:
        pass

    print("dropped:", manager.live_points_dropped)
    manager.stop()
    manager.join()


if __name__ == "__main__":
    main()

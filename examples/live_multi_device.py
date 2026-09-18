"""Live data of several USB devices at 10 Hz: print the LDSA of every point as it arrives.

Usage: python live_multi_device.py        (stop with Ctrl+C)
"""

import queue

from naneos import NaneosDeviceDataPoint, NaneosDeviceManager


def main() -> None:
    # Bounded: if this loop falls behind, the oldest points are dropped.
    live: queue.Queue[NaneosDeviceDataPoint] = queue.Queue(maxsize=10_000)

    manager = NaneosDeviceManager(
        use_ble=False,  # the rate can only be set on USB
        upload_active=False,
        serial_gain_test=False,  # otherwise the data is held back for 10+ s after a connect
        sample_rate_hz=10,  # every device, also the ones plugged in later
    )
    manager.register_live_queue(live)
    manager.start()

    try:
        while True:
            point = live.get()
            print(f"SN{point.serial_number}: LDSA {point.ldsa:6.1f} um^2/cm^3")
    except KeyboardInterrupt:
        pass

    print("dropped:", manager.live_points_dropped)
    manager.stop()
    manager.join()


if __name__ == "__main__":
    main()

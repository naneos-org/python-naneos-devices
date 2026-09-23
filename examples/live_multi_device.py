"""Live data of several USB devices at 10 Hz: print the LDSA of every point as it arrives.

The first device that delivers data is also asked for its serial number with a query.

Usage: python live_multi_device.py        (stop with Ctrl+C)
"""

import queue

from naneos import NaneosDeviceDataPoint, NaneosDeviceManager


def main() -> None:
    # Bounded: if this loop falls behind, the oldest points are dropped.
    live: queue.Queue[NaneosDeviceDataPoint] = queue.Queue(maxsize=10_000)

    manager = NaneosDeviceManager(
        use_ble=False,  # the rate can only be set on USB
        upload_active=True,
        serial_gain_test=False,  # otherwise the data is held back for 10+ s after a connect
        sample_rate_hz=None,  # every device, also the ones plugged in later
    )
    manager.register_live_queue(live)
    manager.start()

    # try:
    #     while True:
    #         time.sleep(10)
    #         test_pulse = manager.read_pulse_form(8112)
    #         # resp = manager._try_upload(test_pulse)
    #         # print(f"Pulse Upload: {resp}")

    #         print(len(test_pulse.currents))
    #         print(test_pulse.currents)

    # except KeyboardInterrupt:
    #     pass

    queried = False
    try:
        while True:
            point = live.get()
            if not queried:  # the first point tells us which device is there
                # a command with an answer, sent from the loop thread while the data keeps coming
                print("N? ->", manager.query(point.serial_number, "N?"))  # -> ["8617"]
                queried = True
            print(f"SN{point.serial_number}: LDSA {point.ldsa:6.1f} um^2/cm^3")
    except KeyboardInterrupt:
        pass

    print("dropped:", manager.live_points_dropped)
    manager.stop()
    manager.join()


if __name__ == "__main__":
    main()

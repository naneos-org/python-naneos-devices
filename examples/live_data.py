"""Live data: every data point the moment it arrives, instead of snapshots every 10+ s.

Usage: python live_data.py        (stop with Ctrl+C)
"""

import queue
import time

from naneos import NaneosDeviceDataPoint, NaneosDeviceManager


def main() -> None:
    # Bounded: if this loop falls behind, the oldest points are dropped.
    live: queue.Queue[NaneosDeviceDataPoint] = queue.Queue(maxsize=10_000)

    manager = NaneosDeviceManager(upload_active=False)  # the upload works alongside, if wanted
    manager.register_live_queue(live)
    manager.start()

    try:
        while True:
            point = live.get()
            age_ms = time.time() * 1000 - (point.unix_timestamp or 0)
            print(
                f"SN{point.serial_number} via {point.connection_type}: "
                f"LDSA {point.ldsa} um^2/cm^3, {age_ms:.0f} ms old"
            )
    except KeyboardInterrupt:
        pass

    print("dropped:", manager.live_points_dropped)
    manager.stop()
    manager.join()


if __name__ == "__main__":
    main()

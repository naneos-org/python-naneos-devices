"""Process the data yourself: every snapshot arrives on a queue as pandas DataFrames.

Usage: python queue_handoff.py        (stop with Ctrl+C)
"""

import queue
import time

from naneos import NaneosDeviceManager


def main() -> None:
    snapshots: queue.Queue = queue.Queue()

    manager = NaneosDeviceManager(
        upload_active=False,  # we handle the data ourselves
        gathering_interval_seconds=15,
    )
    manager.register_output_queue(snapshots)
    manager.start()

    try:
        while True:
            time.sleep(manager.seconds_until_next_snapshot + 1)

            while not snapshots.empty():
                snapshot = snapshots.get()  # dict[int, pandas.DataFrame], keyed by serial number
                print(f"Received snapshot for {len(snapshot)} device(s)")
                for serial_number, df in snapshot.items():
                    print(f"  SN{serial_number}: {len(df)} rows, mean LDSA {df['ldsa'].mean():.1f}")
                    # >>> your processing here (store, analyse, forward, ...)
    except KeyboardInterrupt:
        pass

    manager.stop()
    manager.join()


if __name__ == "__main__":
    main()

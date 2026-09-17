"""Talk to the devices: send commands, read answers, set the data rate.

The API is the same over USB and BLE. Only the data rate is USB only.

Usage: python device_commands.py
"""

import queue
import time

from naneos import NaneosDeviceManager, NotSupportedError


def main() -> None:
    snapshots: queue.Queue = queue.Queue()
    manager = NaneosDeviceManager(
        upload_active=False,
        gathering_interval_seconds=10,
        serial_gain_test=False,  # the gain test holds the data back for 10 s after a connect
    )
    manager.register_output_queue(snapshots)
    manager.start()

    print("Waiting for devices...")
    time.sleep(15)

    for device in manager.get_devices():
        print(device)
        print("  firmware:", device.query("f?"))  # a command with an answer -> ["422"]
        device.write("A0002!")  # a command without an answer

        try:
            device.set_sample_rate(10)  # 0 (off), 1, 10 or 100 Hz
            print("  now sampling at 10 Hz")
        except NotSupportedError as e:
            print("  rate unchanged:", e)

    # The output queue gets the data at the rate set above; the upload would stay at 1 Hz.
    while not snapshots.empty():
        snapshots.get()
    snapshots.get(timeout=30)  # the snapshot in progress still has rows at the old rate
    for serial_number, df in snapshots.get(timeout=30).items():
        print(f"SN{serial_number}: {len(df)} rows in 10 s")

    manager.stop()
    manager.join()


if __name__ == "__main__":
    main()

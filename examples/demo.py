import time

from naneos.manager import NaneosDeviceManager


def minimal_example() -> None:
    manager = NaneosDeviceManager(
        use_serial=True,
        use_ble=True,
        upload_active=False,
        gathering_interval_seconds=10,  # clamped to [10, 600]
    )
    manager.start()

    try:
        while True:
            # Sleep exactly until the next publish window
            remaining = manager.get_seconds_until_next_upload()
            print(f"Next upload in: {remaining:.0f}s")
            time.sleep(remaining + 1)

            print("Serial:", manager.get_connected_serial_devices())
            print("BLE   :", manager.get_connected_ble_devices())
            print()
    except KeyboardInterrupt:
        pass

    manager.stop()
    manager.join()
    print("Stopped.")


def queue_example() -> None:
    import queue

    out_q: queue.Queue = queue.Queue()

    manager = NaneosDeviceManager(
        upload_active=True,
        gathering_interval_seconds=10,
        use_ble=True,
        use_serial=True,
    )
    manager.register_output_queue(out_q)
    manager.start()

    try:
        while True:
            time.sleep(manager.get_seconds_until_next_upload() + 1)

            while not out_q.empty():
                snapshot = out_q.get()
                print(f"Received snapshot for {len(snapshot)} device(s)")
                for serial, df in snapshot.items():
                    print(
                        f"  - {serial}: {len(df)} rows, corona_voltage: {df['corona_voltage'].mean():.1f}"
                    )
    except KeyboardInterrupt:
        pass

    manager.stop()
    manager.join()


if __name__ == "__main__":
    queue_example()

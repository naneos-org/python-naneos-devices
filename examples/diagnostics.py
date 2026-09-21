"""The UI curve and the pulse form of a Partector 2: on request, and on the schedule.

Both need firmware 418 or newer and work over USB and BLE alike. The UI curve
sweeps the corona voltage, which takes 10 s and holds the data of the device
back while it settles; the pulse form is read without disturbing anything.

Usage: python diagnostics.py
"""

import queue
import time

from naneos import NaneosDeviceManager, NotSupportedError, PulseForm, UiCurve


def main() -> None:
    manager = NaneosDeviceManager(
        upload_active=False,
        serial_gain_test=False,  # the gain test holds the data back for 10 s after a connect
        diagnostics_interval_hours=1,  # the default: every device, once an hour, at the full hour
    )
    diagnostics: queue.Queue[UiCurve | PulseForm] = queue.Queue()
    manager.register_diagnostics_queue(diagnostics)  # the scheduled readouts land here
    manager.start()

    print("Waiting for devices...")
    time.sleep(15)

    # On request, one device at a time. Over USB this takes about 11 s and 1 s,
    # over BLE about 50 s each: the device sends one packet every 2 s.
    for device in manager.get_devices():
        print(device)
        try:
            curve = device.read_ui_curve()
            print(f"  UI curve: {curve.voltages[0]}-{curve.voltages[-1]} V, ", end="")
            print(
                f"{curve.currents[0]:.2f}-{curve.currents[-1]:.2f} nA, {len(curve.voltages)} points"
            )
            form = device.read_pulse_form()
            print(f"  pulse form: max {max(form.currents):.2f} nA, {len(form.currents)} samples")
        except NotSupportedError as e:
            print("  no diagnostics:", e)
        except (TimeoutError, ConnectionError) as e:
            print("  readout failed:", e)

    # Or all connected devices at once, on a thread of the manager, like the hourly readout.
    manager.request_diagnostics()
    while manager.diagnostics_in_progress or not diagnostics.empty():
        try:
            result = diagnostics.get(timeout=1)
        except queue.Empty:
            continue
        print(f"SN{result.serial_number}: {type(result).__name__} at {result.unix_timestamp}")

    manager.stop()
    manager.join()


if __name__ == "__main__":
    main()

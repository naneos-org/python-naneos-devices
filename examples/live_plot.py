"""Live plot of the diffusion current of one Partector on USB.

Needs matplotlib, which is not a dependency of naneos-devices: pip install matplotlib

Usage: python live_plot.py [serial_number] [sample_rate_hz]
       serial_number   default: the first device that delivers data
       sample_rate_hz  1, 10 or 100 (default)

Close the window to stop.
"""

import queue
import sys
import time
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from naneos import NaneosDeviceDataPoint, NaneosDeviceManager

WINDOW_SECONDS = 10
REFRESH_MS = 500


class LivePlot:
    def __init__(self, serial_number: int | None, sample_rate_hz: int) -> None:
        self.serial_number = serial_number
        self.sample_rate_hz = sample_rate_hz

        # Bounded: if plotting falls behind, the oldest points are dropped.
        self.live: queue.Queue[NaneosDeviceDataPoint] = queue.Queue(maxsize=10_000)
        self.manager = NaneosDeviceManager(
            use_ble=False,  # USB only
            upload_active=False,
            serial_gain_test=False,  # the gain test holds the data back for 10 s after a connect
            sample_rate_hz=sample_rate_hz,  # a P2 Pro leaves its size distribution mode for it
        )
        self.manager.register_live_queue(self.live)

        # Enough room for the whole window at 100 Hz.
        self.times: deque[float] = deque(maxlen=WINDOW_SECONDS * 100)
        self.currents: deque[float] = deque(maxlen=WINDOW_SECONDS * 100)

        self.figure, self.axes = plt.subplots(figsize=(10, 5))
        (self.line,) = self.axes.plot([], [], linewidth=1)
        self.axes.set_xlabel("seconds ago")
        self.axes.set_ylabel("diffusion current [nA]")
        self.axes.set_xlim(-WINDOW_SECONDS, 0)
        self.axes.grid(True, alpha=0.3)
        self.axes.set_title("Waiting for a Partector on USB...")

    def update(self, _frame: int = 0) -> tuple:
        """Take what arrived since the last refresh and redraw the line."""
        while True:
            try:
                point = self.live.get_nowait()
            except queue.Empty:
                break

            if self.serial_number is None:
                self.serial_number = point.serial_number  # the first device to deliver data
            if point.serial_number != self.serial_number or point.diffusion_current is None:
                continue
            if point.unix_timestamp is None:
                continue

            self.times.append(point.unix_timestamp / 1000)
            self.currents.append(point.diffusion_current)

        if self.times:
            now = time.time()
            self.line.set_data([t - now for t in self.times], list(self.currents))
            self.axes.relim()
            self.axes.autoscale_view(scalex=False)
            self.axes.set_title(
                f"SN{self.serial_number}: diffusion current {self.currents[-1]:.2f} nA "
                f"({self.sample_rate_hz} Hz)"
            )
        return (self.line,)

    def run(self) -> None:
        self.manager.start()
        try:
            # Keep a reference: an animation that is garbage collected stops.
            animation = FuncAnimation(  # noqa: F841
                self.figure, self.update, interval=REFRESH_MS, cache_frame_data=False
            )
            plt.show()  # blocks until the window is closed
        except KeyboardInterrupt:
            pass
        finally:
            self.manager.stop()
            self.manager.join()


def main() -> None:
    serial_number = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sample_rate_hz = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    if sample_rate_hz not in (1, 10, 100):
        sys.exit(__doc__)

    LivePlot(serial_number, sample_rate_hz).run()


if __name__ == "__main__":
    main()

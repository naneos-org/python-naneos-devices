"""The UI curve and the pulse form of a Partector over BLE (firmware 418 or newer).

Both come as a stream of 20 byte packets on the aux characteristic, one packet
every 2 s, after "UI?" or "pulse?" (see PartectorBleDiagnosticsPackets). The
reader collects them until the last one and assembles the result.
"""

import asyncio
import time
from collections.abc import Callable

from naneos.ble.partector.characteristics import PartectorBleDiagnosticsPackets
from naneos.ble.partector.commands import BleCommandChannel
from naneos.data_point import DeviceType
from naneos.diagnostics import (
    BLE_READOUT_TIMEOUT_SECONDS,
    PULSE_FORM_VALUES,
    UI_COMPUTE_SECONDS,
    UI_CURVE_POINTS,
    PulseForm,
    UiCurve,
    check_firmware,
)


class BleDiagnosticsReader:
    """Reads the diagnostics of one device. Must be used on the connection's event loop.

    Args:
        serial_number: of the device.
        channel: the commands of the link; a readout holds its lock while it collects.
        firmware_version: the firmware of the device, None while it is not known.
        device_type: the type of the device, None while it is not known.
    """

    def __init__(
        self,
        serial_number: int,
        channel: BleCommandChannel,
        firmware_version: Callable[[], int | None],
        device_type: Callable[[], DeviceType | None],
    ) -> None:
        self._serial_number = serial_number
        self._channel = channel
        self._firmware_version = firmware_version
        self._device_type = device_type

        # The data is held back during a UI curve sweep.
        self.hold_points_until = 0.0

        # A readout in flight: the packets it waits for, and the future that
        # gets them once the last packet is in.
        self._kind: str | None = None  # "ui_curve" / "pulse_form"
        self._packets: list[bytes] = []
        self._future: asyncio.Future[list[bytes]] | None = None

    @property
    def holding_points(self) -> bool:
        """True while a sweep disturbs the measurement: its data points are not published."""
        return time.time() < self.hold_points_until

    async def read_ui_curve(self, timeout: float | None = None) -> UiCurve:
        """See PartectorDevice.read_ui_curve()."""
        check_firmware(self._firmware_version(), "UI curve")
        # The sweep ramps the corona voltage: whatever the device measures
        # meanwhile is not air, and it needs an integration time to recover.
        # The integration time is not known over BLE; 16 s is the longest.
        self.hold_points_until = time.time() + UI_COMPUTE_SECONDS + 16 + 2
        try:
            await self._channel.write("UI!")
        except Exception:
            self.hold_points_until = 0.0  # no sweep started: do not hold back good data
            raise
        await asyncio.sleep(UI_COMPUTE_SECONDS)  # without the command lock

        packets = await self._read_packets("UI?", "ui_curve", timeout)
        points = sorted(
            point
            for packet in packets
            for point in PartectorBleDiagnosticsPackets.ui_curve_points(packet)
        )[:UI_CURVE_POINTS]
        return UiCurve(
            device_type=self._device_type_or_p2(),
            serial_number=self._serial_number,
            unix_timestamp=int(time.time()),
            voltages=tuple(u for u, _ in points),
            currents=tuple(i for _, i in points),
        )

    async def read_pulse_form(self, timeout: float | None = None) -> PulseForm:
        """See PartectorDevice.read_pulse_form()."""
        check_firmware(self._firmware_version(), "pulse form")
        packets = await self._read_packets("pulse?", "pulse_form", timeout)
        # The packets overlap by one sample: place every sample by its index.
        samples = {
            index: value
            for packet in packets
            for index, value in PartectorBleDiagnosticsPackets.pulse_form_values(packet)
        }
        return PulseForm(
            device_type=self._device_type_or_p2(),
            serial_number=self._serial_number,
            unix_timestamp=int(time.time()),
            currents=tuple(samples[i] for i in range(PULSE_FORM_VALUES) if i in samples),
        )

    def on_packet(self, data: bytes) -> None:
        """A UI curve or pulse form packet on the aux characteristic (event loop thread)."""
        future = self._future
        expected_ui = self._kind == "ui_curve"
        if future is None or future.done():
            return  # nobody asked: a readout started by a plain write("UI?")
        if PartectorBleDiagnosticsPackets.is_ui_curve(data) != expected_ui:
            return  # the other kind, left over from an earlier readout
        self._packets.append(data)
        if PartectorBleDiagnosticsPackets.is_last(data):
            future.set_result(self._packets)

    def _device_type_or_p2(self) -> DeviceType:
        kind = self._device_type()
        return DeviceType.P2 if kind is None else kind

    async def _read_packets(self, command: str, kind: str, timeout: float | None) -> list[bytes]:
        """Send a command and collect the diagnostics packets that answer it."""
        async with self._channel.lock:
            self._kind = kind
            self._packets = []
            self._future = asyncio.get_running_loop().create_future()
            try:
                await self._channel.write_locked(command)
                return await asyncio.wait_for(
                    asyncio.shield(self._future),
                    timeout or BLE_READOUT_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                raise TimeoutError(
                    f"SN{self._serial_number}: {command!r} answered {len(self._packets)} packets."
                ) from None
            finally:
                self._kind = None
                self._future = None

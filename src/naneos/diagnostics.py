"""The two diagnostics a Partector 2 reads out on request: the UI curve and the pulse form.

Both need firmware 418 or newer and are read the same way over USB and BLE
(see PartectorDevice.read_ui_curve / read_pulse_form). Each goes to the naneos
IoT service as a message of its own, apart from the measurement data.
"""

from dataclasses import dataclass

from naneos.data_point import DeviceType

MIN_FIRMWARE = 418
UI_CURVE_POINTS = 100
PULSE_FORM_VALUES = 200
# "UI!" starts the corona voltage sweep, "UI?" reads the result. The device
# needs this long to compute the curve; asked earlier, it answers with nothing.
UI_COMPUTE_SECONDS = 10.0
# From "UI?" / "pulse?" to the last point. Over USB the whole answer comes
# within a second; over BLE the device sends one packet every 2 s, so a UI
# curve takes 40 s and a pulse form 50 s.
READOUT_TIMEOUT_SECONDS = 30.0
BLE_READOUT_TIMEOUT_SECONDS = 90.0


@dataclass(frozen=True)
class UiCurve:
    """The electrometer current over the corona voltage, 100 points sorted by voltage."""

    device_type: DeviceType
    serial_number: int
    unix_timestamp: int  # seconds, when the curve was read
    voltages: tuple[int, ...]  # V
    currents: tuple[float, ...]  # nA

    @property
    def is_complete(self) -> bool:
        return len(self.voltages) == UI_CURVE_POINTS and len(self.currents) == UI_CURVE_POINTS


@dataclass(frozen=True)
class PulseForm:
    """The electrometer current along one charging pulse, 200 samples in time order."""

    device_type: DeviceType
    serial_number: int
    unix_timestamp: int  # seconds, when the form was read
    currents: tuple[float, ...]  # nA

    @property
    def is_complete(self) -> bool:
        return len(self.currents) == PULSE_FORM_VALUES


def raw_to_nanoamperes(raw: int) -> float:
    """The devices report their electrometer currents as nA * 100."""
    return raw / 100.0


def check_firmware(firmware_version: int | None, feature: str) -> None:
    """Raise NotSupportedError unless the firmware is new enough for the feature."""
    from naneos.device import NotSupportedError  # circular at module level

    if firmware_version is None:
        raise NotSupportedError(f"The firmware version is not known yet: no {feature} until then.")
    if firmware_version < MIN_FIRMWARE:
        raise NotSupportedError(
            f"The {feature} needs firmware {MIN_FIRMWARE} or newer, "
            f"this device has {firmware_version}."
        )

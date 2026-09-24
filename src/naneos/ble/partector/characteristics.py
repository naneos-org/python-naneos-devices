"""Decoders for the BLE characteristics and advertisement payloads of a Partector.

Every payload is a fixed 20 byte layout of little-endian unsigned integers.
Each decoder is a table of fields (name, byte slice, scaling); the generic
decode() loop reads them onto a NaneosDeviceDataPoint. Only the size
distribution packs its channels as 20 bit values and needs its own loop.
"""

from dataclasses import dataclass

from naneos.data_point import NaneosDeviceDataPoint
from naneos.diagnostics import raw_to_nanoamperes


@dataclass(frozen=True)
class Field:
    name: str
    offset: slice
    factor: float = 1.0
    divisor: float = 1.0
    cast: type = float

    def read(self, data: bytes) -> float | int:
        raw = int.from_bytes(data[self.offset], byteorder="little")
        return self.cast(raw * self.factor / self.divisor)


class PartectorBleDecoderBlueprint:
    """Shared decode loop. Subclasses define FIELDS or override _decode_fields()."""

    FIELDS: tuple[Field, ...] = ()
    FIELD_NAMES: frozenset[str] = frozenset()

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        # Derive the names from the table unless the subclass lists them itself.
        if cls.FIELDS and "FIELD_NAMES" not in cls.__dict__:
            cls.FIELD_NAMES = frozenset(f.name for f in cls.FIELDS)

    @classmethod
    def decode(
        cls, data: bytes, data_structure: NaneosDeviceDataPoint | None = None
    ) -> NaneosDeviceDataPoint:
        """Decode the payload. If data_structure is given it is filled in place and returned."""
        point = data_structure if data_structure is not None else NaneosDeviceDataPoint()
        for name, value in cls._decode_fields(data).items():
            setattr(point, name, value)
        return point

    @classmethod
    def _decode_fields(cls, data: bytes) -> dict[str, float | int]:
        return {field.name: field.read(data) for field in cls.FIELDS}


class PartectorBleDecoderStd(PartectorBleDecoderBlueprint):
    """The std characteristic, also the first half of the advertisement."""

    FIELDS = (
        Field("serial_number", slice(14, 16), cast=int),
        Field("ldsa", slice(0, 3), factor=0.01),
        Field("average_particle_diameter", slice(3, 5)),
        Field("particle_number_concentration", slice(5, 8)),
        Field("temperature", slice(8, 9)),
        Field("relative_humidity", slice(9, 10)),
        Field("battery_voltage", slice(12, 14), factor=0.01),
        Field("particle_mass", slice(16, 19), factor=0.01),
    )
    FIELD_NAMES = frozenset(f.name for f in FIELDS) | {"device_status"}

    OFFSET_DEVICE_STATE_LOW = slice(10, 12)
    INDEX_DEVICE_STATE_HIGH = 19

    @classmethod
    def get_serial_number(cls, data: bytes) -> int:
        return int(int.from_bytes(data[slice(14, 16)], byteorder="little"))

    @classmethod
    def _decode_fields(cls, data: bytes) -> dict[str, float | int]:
        fields = super()._decode_fields(data)
        # 16 status bits, plus 7 more packed into the upper bits of byte 19.
        status = int.from_bytes(data[cls.OFFSET_DEVICE_STATE_LOW], byteorder="little")
        status += ((int(data[cls.INDEX_DEVICE_STATE_HIGH]) >> 1) & 0b01111111) << 16
        fields["device_status"] = status
        return fields


class PartectorBleDecoderAux(PartectorBleDecoderBlueprint):
    """The aux characteristic, also the scan response half of the advertisement."""

    FIELDS = (
        Field("corona_voltage", slice(0, 2)),
        Field("diffusion_current", slice(2, 4), factor=0.01),
        Field("deposition_voltage", slice(4, 6)),
        Field("flow_from_dp", slice(6, 8), divisor=1000.0),
        Field("ambient_pressure", slice(8, 10)),
        Field("electrometer_1_amplitude", slice(10, 12)),
        Field("electrometer_2_amplitude", slice(12, 14)),
        Field("electrometer_1_gain", slice(14, 16)),
        Field("electrometer_2_gain", slice(16, 18)),
        Field("diffusion_current_offset", slice(18, 20)),
    )


class PartectorBleDecoderAuxError(PartectorBleDecoderBlueprint):
    """The aux characteristic in error mode, marked by 0xFFFF in the first two bytes."""

    MARKER = b"\xff\xff"

    FIELDS = (
        Field("device_status", slice(2, 6), cast=int),
        Field("diffusion_current_delay_on", slice(6, 7), cast=int),
        Field("diffusion_current_delay_off", slice(7, 8), cast=int),
        Field("diffusion_current_average", slice(8, 10), factor=0.01),
        Field("diffusion_current_stddev", slice(10, 12), factor=0.01),
        Field("diffusion_current_max", slice(12, 14), factor=0.01),
        Field("corona_voltage_onset", slice(14, 16), cast=int),
    )

    @classmethod
    def is_error_frame(cls, data: bytes) -> bool:
        return len(data) >= 2 and bytes(data[:2]) == cls.MARKER


class PartectorBleDecoderSize(PartectorBleDecoderBlueprint):
    """The size distribution: 8 channels packed as consecutive 20 bit values."""

    CHANNELS = ("10", "16", "26", "43", "70", "114", "185", "300")
    FIELD_NAMES = frozenset(f"particle_number_{ch}nm" for ch in CHANNELS)
    BITS_PER_CHANNEL = 20

    @classmethod
    def _decode_fields(cls, data: bytes) -> dict[str, float | int]:
        packed = int.from_bytes(data[:20], byteorder="little")
        mask = (1 << cls.BITS_PER_CHANNEL) - 1
        return {
            f"particle_number_{channel}nm": float((packed >> (cls.BITS_PER_CHANNEL * i)) & mask)
            for i, channel in enumerate(cls.CHANNELS)
        }


class PartectorBleDiagnosticsPackets:
    """The UI curve and the pulse form, which the device streams on the aux
    characteristic after "UI?" and "pulse?" (firmware 418 or newer).

    Byte 1 tells the kind, byte 0 is 254 on the last packet and 255 before,
    then the points follow from byte 2. A UI curve packet carries 5 points of
    uint16 LE voltage in V plus uint8 current in nA * 100 (20 packets); its
    last byte counts the packet, 0 to 19. A pulse form packet carries 8 samples
    of uint8 index plus uint8 current in nA * 100 (25 packets of 8 make the 200
    samples, without overlap). Bytes 18 and 19 of a pulse form packet are
    reserved: the firmware leaves the first sample of the next packet there,
    which must not be read as a sample of this one. The device sends one packet
    every 2 s.
    """

    KIND_UI_CURVE = 254
    KIND_PULSE_FORM = 253
    LAST_PACKET = 254
    UI_POINTS_PER_PACKET = 5
    PULSE_VALUES_PER_PACKET = 8

    @classmethod
    def is_ui_curve(cls, data: bytes) -> bool:
        return len(data) >= 2 and data[0] in (254, 255) and data[1] == cls.KIND_UI_CURVE

    @classmethod
    def is_pulse_form(cls, data: bytes) -> bool:
        return len(data) >= 2 and data[0] in (254, 255) and data[1] == cls.KIND_PULSE_FORM

    @classmethod
    def is_diagnostics(cls, data: bytes) -> bool:
        return cls.is_ui_curve(data) or cls.is_pulse_form(data)

    @classmethod
    def is_last(cls, data: bytes) -> bool:
        return data[0] == cls.LAST_PACKET

    @classmethod
    def ui_curve_points(cls, data: bytes) -> list[tuple[int, float]]:
        """(voltage in V, current in nA) per point."""
        points = []
        for i in range(cls.UI_POINTS_PER_PACKET):
            offset = 2 + 3 * i
            voltage = int.from_bytes(data[offset : offset + 2], byteorder="little")
            points.append((voltage, raw_to_nanoamperes(data[offset + 2])))
        return points

    @classmethod
    def pulse_form_values(cls, data: bytes) -> list[tuple[int, float]]:
        """(sample index, current in nA) per sample."""
        return [
            (data[2 + 2 * i], raw_to_nanoamperes(data[2 + 2 * i + 1]))
            for i in range(cls.PULSE_VALUES_PER_PACKET)
        ]

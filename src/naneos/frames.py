"""pandas DataFrame helpers for NaneosDeviceDataPoint lists.

Frames are indexed by unix_timestamp (ms) and keyed by serial number in the
dict[int, pd.DataFrame] structures that flow from the managers to the upload.
"""

from collections.abc import Callable

import pandas as pd

from naneos.data_point import ConnectionType, DeviceType, NaneosDeviceDataPoint
from naneos.logger import get_naneos_logger

logger = get_naneos_logger(__name__)

# What a manager keeps per device when nobody calls its get_data().
# NaneosDeviceManager drains every second, so this only matters for a manager
# that is used on its own and polled rarely.
#
# The BLE links deliver 1 Hz, so they are capped by rows. Serial frames are
# capped by time instead: a row cap that holds five minutes at 1 Hz would hold
# three seconds of a device read at 100 Hz.
MAX_ROWS_PER_DEVICE = 300
MAX_BUFFER_SECONDS = 300

# connection_type is deliberately not listed: it stays a plain object column so
# that comparisons never produce a nullable mask.
PANDAS_DTYPES_MAPPING: dict[str, str] = {
    "unix_timestamp": "Int64",
    "serial_number": "Int32",
    "firmware_version": "Int32",
    "device_type": "Int32",
    "device_status": "Int32",
    "runtime_min": "Float32",
    "ldsa": "Float32",
    "particle_number_concentration": "Float32",
    "average_particle_diameter": "Float32",
    "particle_mass": "Float32",
    "particle_surface": "Float32",
    "diffusion_current": "Float32",
    "diffusion_current_offset": "Float32",
    "diffusion_current_average": "Float32",
    "diffusion_current_stddev": "Float32",
    "diffusion_current_max": "Float32",
    "diffusion_current_delay_on": "Float32",
    "diffusion_current_delay_off": "Float32",
    "corona_voltage": "Float32",
    "corona_voltage_onset": "Float32",
    "hires_adc1": "Float32",
    "hires_adc2": "Float32",
    "electrometer_1_amplitude": "Float32",
    "electrometer_2_amplitude": "Float32",
    "electrometer_1_gain": "Float32",
    "electrometer_2_gain": "Float32",
    "temperature": "Float32",
    "relative_humidity": "Float32",
    "deposition_voltage": "Float32",
    "battery_voltage": "Float32",
    "flow_from_dp": "Float32",
    "ambient_pressure": "Float32",
    "channel_pressure": "Float32",
    "differential_pressure": "Float32",
    "pump_voltage": "Float32",
    "pump_current": "Float32",
    "pump_pwm": "Float32",
    "particle_number_10nm": "Float32",
    "particle_number_16nm": "Float32",
    "particle_number_26nm": "Float32",
    "particle_number_43nm": "Float32",
    "particle_number_70nm": "Float32",
    "particle_number_114nm": "Float32",
    "particle_number_185nm": "Float32",
    "particle_number_300nm": "Float32",
    "sigma_size_dist": "Float32",
    "steps_inversion": "Float32",
    "current_dist_0": "Float32",
    "current_dist_1": "Float32",
    "current_dist_2": "Float32",
    "current_dist_3": "Float32",
    "current_dist_4": "Float32",
    "supply_voltage_5V": "Float32",
    "positive_voltage_3V3": "Float32",
    "negative_voltage_3V3": "Float32",
    "usb_cc_voltage": "Float32",
}


def _apply_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {c: PANDAS_DTYPES_MAPPING[c] for c in df.columns if c in PANDAS_DTYPES_MAPPING}
    try:
        return df.astype(mapping)
    except (TypeError, ValueError) as e:
        # Keep the data flowing, but make the mismatch visible instead of
        # hiding it behind errors="ignore" forever.
        logger.warning(f"Could not apply the column dtypes, keeping raw types: {e}")
        return df.astype(mapping, errors="ignore")


def to_pandas_df(points: list[NaneosDeviceDataPoint]) -> pd.DataFrame:
    """Build a single DataFrame from many data points, indexed by unix_timestamp.

    Points are converted in one batch: a DataFrame construction, an astype and
    a concat per point is the single most expensive thing this library does
    on a Raspberry Pi Zero 2 W.
    """
    if not points:
        return pd.DataFrame()

    df = pd.DataFrame([p.to_dict(remove_nan=False) for p in points])
    df = _apply_dtypes(df)
    df = df.set_index(["unix_timestamp"], drop=True)
    # A point that never received a timestamp cannot be placed on the time axis.
    return df[df.index.notna()]


def add_data_points_to_dict(
    devices: dict[int, pd.DataFrame], points: list[NaneosDeviceDataPoint]
) -> dict[int, pd.DataFrame]:
    """Append data points to the per-serial frames, one pandas round per device."""
    by_serial: dict[int, list[NaneosDeviceDataPoint]] = {}
    for point in points:
        if point.serial_number is None:
            continue
        by_serial.setdefault(point.serial_number, []).append(point)

    for serial, serial_points in by_serial.items():
        new_rows = to_pandas_df(serial_points)
        if new_rows.empty:
            continue

        existing = devices.get(serial)
        if existing is None or existing.empty:
            devices[serial] = new_rows
        else:
            devices[serial] = pd.concat([existing, new_rows], ignore_index=False)

        # Only look at the index once the frame could be over the limit at 1 Hz.
        df = devices[serial]
        if len(df) > MAX_BUFFER_SECONDS:
            oldest_kept = int(df.index.max()) - MAX_BUFFER_SECONDS * 1000
            devices[serial] = df[df.index > oldest_kept]

    return devices


def add_to_existing_naneos_data(
    data: dict[int, pd.DataFrame], new_data: dict[int, pd.DataFrame]
) -> dict[int, pd.DataFrame]:
    """Merge a second dict of frames into the first, concatenating per serial."""
    for serial, df in new_data.items():
        if serial in data:
            data[serial] = pd.concat([data[serial], df], ignore_index=False)
        else:
            data[serial] = df

    return data


def _resolve_device_type(df: pd.DataFrame) -> pd.DataFrame:
    """Give every row the most specific device type seen for this device.

    The type is a property of the device, not of the row, but it is learned
    late: a BLE link reports a P2 Pro only once the first size distribution
    arrives.
    """
    if "device_type" not in df.columns:
        return df

    known = df["device_type"].dropna()
    if known.empty:
        return df

    df = df.copy()
    df["device_type"] = int(known.max())
    return df


def sort_and_clean_naneos_data(
    data: dict[int, pd.DataFrame], serial_only: list[int | None] | None = None
) -> dict[int, pd.DataFrame]:
    """Prepare gathered frames for the upload.

    Per device: keep only the rows of the best connection type (serial over
    BLE link), sort by time, drop duplicate timestamps (last wins) and settle
    on one device type. Devices listed in serial_only are restricted to their
    serial rows even if none arrived.
    """
    if serial_only is None:
        serial_only = []

    data_return: dict[int, pd.DataFrame] = {}

    for serial, df in data.items():
        if serial is None or df.empty:
            continue

        if "connection_type" in df.columns:
            connection = df["connection_type"]
            if (connection == ConnectionType.SERIAL).any() or serial in serial_only:
                df = df[connection == ConnectionType.SERIAL]
            elif (connection == ConnectionType.CONNECTED).any():
                df = df[connection == ConnectionType.CONNECTED]

        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]
        df = _resolve_device_type(df)

        if not df.empty:
            data_return[serial] = df

    return data_return


def aggregate_duplicate_index(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse rows that share an index label into one row per label.

    Used by the upload after the index has been rounded to whole seconds: a
    device read at 10 Hz or 100 Hz must still reach the backend at 1 Hz.
    Measurements are averaged, device_status is OR-ed so that an error flagged
    in any sample survives, everything else keeps its last known value.
    """
    if not df.index.has_duplicates:
        return df  # the normal 1 Hz case, nothing to do

    def bitwise_or(values: pd.Series) -> object:
        known = values.dropna()
        if known.empty:
            return pd.NA
        result = 0
        for value in known:
            result |= int(value)
        return result

    aggregations: dict[str, str | Callable[[pd.Series], object]] = {}
    for column in df.columns:
        if column == "device_status":
            aggregations[column] = bitwise_or
        elif pd.api.types.is_float_dtype(df[column].dtype):
            aggregations[column] = "mean"
        else:
            aggregations[column] = "last"

    aggregated = df.groupby(level=0, sort=True).agg(aggregations)
    return aggregated.astype(df.dtypes.to_dict())


def device_type_of(df: pd.DataFrame, default: DeviceType = DeviceType.P2) -> DeviceType:
    """The device type recorded in a frame, or default when none is known."""
    if "device_type" not in df.columns:
        return default
    known = df["device_type"].dropna()
    if known.empty:
        return default
    return DeviceType(int(known.iloc[-1]))

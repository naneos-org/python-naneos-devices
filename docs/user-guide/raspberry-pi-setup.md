# Raspberry Pi Setup

A Raspberry Pi (a Zero 2 W is enough) can run as an always-on uploader: it connects
to every Partector in reach over USB and Bluetooth and uploads the data to the naneos
IoT service every 30 seconds.

## 1. Operating system

Flash **Raspberry Pi OS Bookworm or newer** (Python 3.11 or newer is required) with the
[Raspberry Pi Imager](https://www.raspberrypi.com/software/). Headless is fine, but you
need SSH access, because the installer runs in a terminal on the Pi. Set up WiFi in the
imager so the Pi has internet access after the first boot.

## 2. Run the installer

```bash
curl -fsSL https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install.sh | sudo bash
```

The installer

* installs `python3-venv` and `iw`,
* creates a virtual environment in `~/naneos-uploader` and installs `naneos-devices` from the
  `master` branch of the repository,
* writes the `naneos_uploader` systemd service, which runs the `naneos-uploader` command as
  your user and restarts it on failure and on every boot,
* switches Bluetooth on, starts `bluetoothd` with `--experimental` (needed for passive BLE
  scanning) and disables WiFi power save (on a Pi Zero 2 W the sleeping WiFi link stalls
  uploads and costs Bluetooth airtime, the two radios share one antenna),
* sets the BLE supervision timeout to 5 s (`ConnectionSupervisionTimeout=500` in
  `/etc/bluetooth/main.conf`). With the BlueZ default of 420 ms a short WiFi burst on the
  shared antenna is enough to drop a link, which shows as a reconnect every few seconds.
  On a Pi that was already running, reboot once afterwards: the kernel keeps the old value
  for devices it already knows.

It does not upgrade the operating system; run `sudo apt full-upgrade` yourself if you want
that.

To install a release tag or a test branch instead of `master`:

```bash
curl -fsSL https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install.sh | sudo bash -s -- --ref v2.0.0
```

To try a release candidate that was published to TestPyPI (see
[Releasing](../development/contributing.md#releasing)), pass its version, or `latest` for the
newest upload:

```bash
curl -fsSL https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install.sh | sudo bash -s -- --testpypi 2.0.4rc1
```

Only the `naneos-devices` wheel comes from TestPyPI, its dependencies are installed from PyPI as
usual. The first log line of the service names the wheel it runs. Re-run the installer without the
option to go back to `master`.

## 3. Check that it runs

```bash
sudo systemctl status naneos_uploader.service
journalctl -u naneos_uploader.service -f
```

The log shows the devices as they connect (`Starting serial manager`, `New device detected`,
`Connected to ...`) and `Upload success: True` every interval.

Bluetooth is connection-only: only devices with an open link deliver data, advertisements
are used to find them. The scanner should report `BLE scanning (passive).` shortly after
start. If it says `(active)` together with a warning, BlueZ refused passive scanning; check
that `systemctl show bluetooth -p ExecStart` contains `--experimental` and that
`bluetoothctl --version` is 5.56 or newer.

To restrict the Pi to your own devices, or to limit the number of links, edit the service:

```bash
sudo systemctl edit naneos_uploader.service
```

and add, for example:

```ini
[Service]
ExecStart=
ExecStart=/home/pi/naneos-uploader/.venv/bin/naneos-uploader --ble-allow 8617,8764 --ble-max-links 2
```

followed by `sudo systemctl restart naneos_uploader.service`.

If the links drop every few seconds (`Disconnect callback called` followed by
`Connected to ...`), check the supervision timeout while the service connects:

```bash
sudo timeout 40 btmon -T 2>/dev/null | grep -i "supervision timeout" | sort | uniq -c &
sleep 2; sudo systemctl restart naneos_uploader.service; wait
```

It has to print `5000 msec`. If it prints `420 msec`, reboot the Pi.

## 4. Upgrading

Re-run the installer. It keeps the virtual environment, installs the newer package and
restarts the service.

## Running it by hand

Stop the service first, then run the command with the options you need, for example to
watch the devices without uploading anything:

```bash
sudo systemctl stop naneos_uploader.service
~/naneos-uploader/.venv/bin/naneos-uploader --no-upload --interval 10 --log-level DEBUG
```

`naneos-uploader --help` lists all options.

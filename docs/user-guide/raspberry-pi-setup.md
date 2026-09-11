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
* switches Bluetooth on and disables WiFi power save (on a Pi Zero 2 W the sleeping WiFi
  link stalls uploads and costs Bluetooth airtime, the two radios share one antenna).

It does not upgrade the operating system; run `sudo apt full-upgrade` yourself if you want
that.

To install a release tag or a test branch instead of `master`:

```bash
curl -fsSL https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install.sh | sudo bash -s -- --ref v1.2.0
```

## 3. Check that it runs

```bash
sudo systemctl status naneos_uploader.service
journalctl -u naneos_uploader.service -f
```

The log shows the devices as they connect (`Starting serial manager`, `New device detected`,
`Connected to ...`) and `Upload success: True` every interval.

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

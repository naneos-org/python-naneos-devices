# Raspberry Pi Setup

A Raspberry Pi (a Zero 2 W is enough) can run as an always-on uploader: it connects
to every Partector in reach over USB and Bluetooth and uploads the data to the naneos
IoT service every 30 seconds.

Tested hardware: **Raspberry Pi Zero 2 W** (recommended) and **Raspberry Pi Zero W**
(1st generation). The Zero W works, but it is old hardware with a single 32-bit core and
512 MB of RAM: the installation takes a long time and so does every boot before the
uploader is running. The installer detects the 32-bit system and installs the extra
OpenBLAS packages the numpy build for it needs.

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
* creates a virtual environment in `~/naneos-uploader` and installs the newest release of
  `naneos-devices` from [PyPI](https://pypi.org/project/naneos-devices/),
* writes the `naneos_uploader` systemd service, which runs the `naneos-uploader` command as
  your user and restarts it on failure and on every boot,
* puts `naneos-uploader-change.txt` and `naneos-uploader-current.txt` on the boot partition,
  through which the options of the service can be changed, a WiFi network added and automatic
  updates switched without SSH (see [Changing the options](#4-changing-the-options)),
* writes the `naneos_uploader_update` timer for
  [automatic updates](#automatic-updates), off unless `--auto-update` is given,
* switches Bluetooth on, starts `bluetoothd` with `--experimental` (needed for passive BLE
  scanning) and disables WiFi power save (on a Pi Zero 2 W the sleeping WiFi link stalls
  uploads and costs Bluetooth airtime, the two radios share one antenna),
* keeps the systemd journal in RAM (`Storage=volatile` in
  `/etc/systemd/journald.conf.d/naneos-volatile.conf`). The service logs a few lines every
  interval, and that was the only regular write to the SD card. A Pi that is switched off by
  pulling the plug can corrupt the card during a write, so nothing is written during normal
  operation. The log is gone after a reboot: `journalctl` shows the current boot only. For a
  persistent log while debugging, delete that file and reboot,
* sets the BLE supervision timeout to 5 s (`ConnectionSupervisionTimeout=500` in
  `/etc/bluetooth/main.conf`). With the BlueZ default of 420 ms a short WiFi burst on the
  shared antenna is enough to drop a link, which shows as a reconnect every few seconds.
  On a Pi that was already running, reboot once afterwards: the kernel keeps the old value
  for devices it already knows.

It does not upgrade the operating system; run `sudo apt full-upgrade` yourself if you want
that.

Re-running the installer upgrades to the newest release. To install another version, add one of
these options after `sudo bash -s --`:

| Option | Installs |
|---|---|
| `--version 2.0.4rc1` | exactly this version from PyPI, for example a release candidate |
| `--pre` | the newest version on PyPI with pre-releases included: `2.0.4rc1` while that is the newest upload, `2.0.4` once it is released |
| `--ref release_test` | a git branch or tag from GitHub instead of PyPI, for code that is not released yet |
| `--auto-update` / `--no-auto-update` | switch [automatic updates](#automatic-updates) on or off; without either, a re-run keeps the current setting (off on a fresh installation) |

For example, the newest release with automatic updates switched on:

```bash
curl -fsSL https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install.sh | sudo bash -s -- --auto-update
```

or exactly one version, for example a release candidate:

```bash
curl -fsSL https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install.sh | sudo bash -s -- --version 2.0.4rc1
```

The dependencies are always stable releases. The first log line of the service tells where the
package came from (`PyPI` or the git archive URL).

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

## 4. Changing the options

To restrict the Pi to your own devices, limit the number of Bluetooth links or change the
interval, you set options of the `naneos-uploader` command. There are two ways.

### From the SD card, without SSH

The boot partition of the card is FAT and opens on any Computer. It holds two
files:

| File | Purpose |
|---|---|
| `naneos-uploader-change.txt` | Write the new options here. They are applied at the next boot, and the file is then reset to its commented template. |
| `naneos-uploader-current.txt` | Written at every boot: the options the service runs with. Editing it has no effect. |

Switch the Pi off, put the card into the PC, open `naneos-uploader-change.txt` in Notepad or
TextEdit, remove the `#` in front of the `OPTIONS` line and write the options after the `=`,
exactly as you would on the command line:

```ini
OPTIONS=--ble-allow 8617,8764 --ble-max-links 2
```

Put the card back and switch the Pi on. `OPTIONS=` with nothing after the `=` restores the
defaults. The file lists all options with a short explanation.

The same file adds a WiFi network, for example before the Pi moves to another site:

```ini
WIFI_SSID=Office
WIFI_PASSWORD=the-office-password
```

The network is added to the ones the Pi already knows as a NetworkManager profile with a
higher priority, nothing is removed, so a typo cannot cut the Pi off the network it has.
WPA2 and WPA3 personal are supported (password of 8 to 63 characters), enterprise networks
with a user name and certificate are not. The WiFi country has to be set already, which the
Raspberry Pi Imager does. The password is stored root-only on the Pi and removed from the
card at boot, when the file is reset. Until that boot it sits in plain text on the card,
the same as with the Imager's own WiFi setup. `naneos-uploader-current.txt` lists the names
of the known networks and never the password.

The file also switches [automatic updates](#automatic-updates):

```ini
AUTO_UPDATE=on
```

`on` or `off`. The current file shows the state after each boot.

Every line is checked before anything is applied: the options with the uploader's own
argument parser, the WiFi lines for length and characters, `AUTO_UPDATE` for `on` or `off`.
If one line fails, nothing from the file is applied, the previous settings stay in use, and
both files start with a `# !!` block naming the error and the rejected lines (password
masked), so the service always comes up.

Behind the scenes the `naneos_uploader_settings` service (`naneos-uploader-settings`, part of
the package) runs before the uploader, stores the options in
`/etc/naneos-uploader/options.env`, and the uploader unit expands them in its `ExecStart`. Its
log is in `journalctl -u naneos_uploader_settings.service`. Over SSH the same happens without a
reboot with `sudo systemctl restart naneos_uploader.service`, which pulls the settings service
in first.

### Over SSH, with systemctl

```bash
sudo systemctl edit naneos_uploader.service
```

and add, for example:

```ini
[Service]
ExecStart=
ExecStart=/home/pi/naneos-uploader/.venv/bin/naneos-uploader --ble-allow 8617,8764 --ble-max-links 2
```

followed by `sudo systemctl restart naneos_uploader.service`. Such an override replaces the
command and wins over the SD card file; `naneos-uploader-current.txt` then says so in a `# !!`
line. Remove it with `sudo systemctl revert naneos_uploader.service` to hand control back to
the file.

## 5. Link problems

If the links drop every few seconds (`Disconnect callback called` followed by
`Connected to ...`), check the supervision timeout while the service connects:

```bash
sudo timeout 40 btmon -T 2>/dev/null | grep -i "supervision timeout" | sort | uniq -c &
sleep 2; sudo systemctl restart naneos_uploader.service; wait
```

It has to print `5000 msec`. If it prints `420 msec`, reboot the Pi.

## 6. Upgrading

Re-run the installer. It keeps the virtual environment, installs the newer package and
restarts the service.

### Automatic updates

Off by default. Switch them on with `--auto-update` on the installer line, with
`AUTO_UPDATE=on` in `naneos-uploader-change.txt` on the SD card, or with
`sudo systemctl enable --now naneos_uploader_update.timer`. All three set the same switch,
the timer, and `--no-auto-update`, `AUTO_UPDATE=off` or `systemctl disable --now` turn it off
again. Re-running the installer without either flag keeps the current setting.

Once a day, between 03:00 and 04:00 local time, the timer runs `naneos-uploader-update`. It
asks PyPI for the newest release, pre-releases excluded, and compares it with the installed
version. If nothing is newer, that is all: one small request, and the service is not
touched. If there is a newer release, it downloads the installer of that release from GitHub
and runs it with `--version`, which installs the package, refreshes the unit files and
configuration, and restarts the service once. At most one interval of buffered data is lost.

A Pi that was off at that time catches up after the next boot. An installation from a git
ref (`--ref`) is never updated automatically. Check the state and the last run with:

```bash
systemctl list-timers naneos_uploader_update.timer
journalctl -u naneos_uploader_update.service
sudo ~/naneos-uploader/.venv/bin/naneos-uploader-update --check
```

## When the internet is down

The uploader keeps what it gathers while the upload does not work and sends it when the
connection is back. It keeps it in **RAM**, never on the SD card, which protects the card but
means: the data is lost when the service restarts (also for an automatic update) or the Pi loses
power during the outage.

The buffer is `--upload-buffer-mb` (default 100). What that holds at 1 Hz, measured with real
device data (all columns of the device present):

| Devices | Data per day | Covered by 100 MB |
|---|---|---|
| 1 P2 | 10 MB | 10 days |
| 1 P2 Pro over Bluetooth (1 Hz) | 15 MB | 6 days |
| 1 P2 + 1 P2 Pro | 25 MB | 4 days |
| 7 P2 (the Bluetooth link limit) | 70 MB | 1.4 days |
| 7 P2 Pro over Bluetooth | 106 MB | 22 hours |

A P2 Pro on USB in size distribution mode gives one row every 6 s and needs a sixth of that.
The rate of a USB device does not matter: 10 and 100 Hz are reduced to 1 Hz before they are kept.
The process takes about 15 % more RAM than the setting, so 100 MB is about 115 MB of a Pi
with 512 MB, on top of the ~80 MB the uploader needs anyway. Lower it for a Pi Zero that runs
other things: `OPTIONS=--upload-buffer-mb 50`.

When the buffer is full the oldest data is dropped and the log says so (at most once a
minute). When the connection is back the backlog is sent oldest first, in requests of up to 10
minutes of data each (at most about 2000 rows of all devices together, so fewer minutes with
many devices), while new data goes into the same queue: a day of data takes a few minutes. During that time the newest data reaches the cloud with a delay. The log says when an
outage starts and how long it lasted.

## Running it by hand

Stop the service first, then run the command with the options you need, for example to
watch the devices without uploading anything:

```bash
sudo systemctl stop naneos_uploader.service
~/naneos-uploader/.venv/bin/naneos-uploader --no-upload --interval 10 --log-level DEBUG
```

`naneos-uploader --help` lists all options.

# Ideas and deferred work

Things we want but have no time for right now. Each entry records the decision already
taken and the open questions, so the work can start without re-deriving it.
`REFACTORING.md` holds the cleanup backlog; this file holds new features.

Legend: `[ ]` open, `[x]` done.

---

## 1. Ready-made Raspberry Pi image for the Imager

Decided 2026-09-21. Goal: a customer without SSH or terminal skills sets up an uploader
with the Raspberry Pi Imager alone. The only per-customer input is WiFi, and the Imager's
own customization dialog asks for that. Uploading needs no token, so nothing else is
customer specific.

### Flashing route: "Use custom"

The customer downloads `naneos-uploader-<version>-arm64.img.xz` from the GitHub release,
opens the Raspberry Pi Imager, picks *Use custom*, selects the file, fills in WiFi, country
and hostname in the customization dialog and flashes the card. First boot applies the WiFi
settings, the uploader service is already enabled and starts on its own.

Rejected for now: a custom Imager repository (`rpi-imager --repo <os_list.json>`), which
lists the image next to Raspberry Pi OS. It needs a shortcut with a command line argument
on the customer's PC, which is exactly the kind of step we want to avoid. The JSON format is
the official `os_list_imagingutility_v4.json` (fields `name`, `description`, `icon`, `url`,
`extract_size`, `extract_sha256`, `image_download_size`, `release_date`, `init_format`,
`devices`), so it can be added later without touching the image.

### Build

- [ ] Build with [pi-gen](https://github.com/RPi-Distro/pi-gen), the tool Raspberry Pi OS
  is built with. Base: Raspberry Pi OS Lite 64-bit (Trixie). Add one stage after `stage2`
  that runs `installers/install.sh` inside the chroot, or a variant of it that skips the
  steps that need a running system (`systemctl restart`, `bluetoothctl power on`, `iw`) and
  only enables the units.
- [ ] Run the build in GitHub Actions on every release tag (for example with
  `usimd/pi-gen-action`) and attach the `.img.xz` plus its sha256 to the release.
- [ ] 64-bit only, target Pi Zero 2 W and newer. The Pi Zero W (1st gen, 32-bit) works
  with the installer but is too slow to support as an image; if we ever want it, it is a
  second pi-gen build with the `armhf` base and the OpenBLAS packages from the installer.
- [ ] The Imager writes WiFi and user settings through the base image's first-boot hook
  (`init_format` is `cloudinit-rpi` on Trixie, `systemd` with `firstrun.sh` on Bookworm).
  Verify after each base upgrade that the dialog still takes effect in our image.

### Updates

An image freezes the version at flash time. Without a way to update, customers stay on
it forever.

- [ ] systemd timer (nightly, randomized delay) that re-runs the pip upgrade step of the
  installer and restarts the service only if the version changed.
- [ ] Alternative: the uploader checks PyPI itself and logs "update available"; a manual
  update path is then still the installer over SSH. Simpler, but does not help customers
  without SSH. Prefer the timer.
- [ ] Keep the current installer working on a flashed image, so a re-run over SSH remains
  the manual upgrade path for us.

### Open questions

- Hostname: a fixed default such as `naneos-uploader` or the Imager's choice? With several
  Pis in one network the customer must set distinct names in the Imager anyway.
- Do we ship the image on GitHub Releases (free, public, size limit 2 GB per file, fine for
  a ~500 MB `.img.xz`) or on naneos infrastructure?
- Locale and time zone: uploads are UTC, so the defaults from the Imager are enough.

---

## 2. Customisation file on the SD card

Implemented 2026-09-21 (`src/naneos/uploader_settings.py`, unit `naneos_uploader_settings`
written by the installer, documented in `docs/user-guide/raspberry-pi-setup.md`). The design
ended up simpler than first planned: no `--config` argument and no key = value parser. The
change file holds one `OPTIONS=` line with the command line options as they are, the same
thing we used to put into `ExecStart` with `systemctl edit`. A root oneshot unit validates the
line with the uploader's argument parser, stores it in an environment file the uploader unit
expands, resets the change file to its template and writes the current file.

- [x] `naneos-uploader-change.txt` and `naneos-uploader-current.txt` on the boot partition.
- [x] Fully commented template, Notepad artifacts (BOM, CRLF, quotes) tolerated.
- [x] A rejected line keeps the previous options and is explained in both files.
- [x] `systemctl edit` overrides still win and are reported in the current file.
- [ ] Ship the two files in the Pi image (section 1) and mention them in the customer
  instructions.
- [ ] Optional: apply `interval`, `ble_allow`, `ble_max_links` and `upload` at runtime
  without a reboot by watching the file. The manager's runtime controls allow it; not
  needed while the card is edited in a PC anyway.
- [x] WiFi: `WIFI_SSID` and `WIFI_PASSWORD` add a NetworkManager profile (root-only
  keyfile, higher autoconnect priority, known networks kept). The password is on the card
  in plain text until the boot that applies it, the same trade-off the Imager makes.
- [ ] Open: `WIFI_COUNTRY` for cards that were never set up with the Imager (the radio
  stays blocked without a country). Not needed as long as the Imager does the first setup.

---

## 3. Surviving hard power-offs: shutdown button, journal cap, read-only root

Noted 2026-09-21. A headless customer Pi is switched off by pulling the plug. The
measurement data does not suffer: the uploader writes nothing to the card, unsent snapshots
live in memory (at most `MAX_PENDING_UPLOADS`, about 10 minutes) and the Partector keeps its
own record. The card does: the journal is written every interval, the two settings files on
the FAT boot partition once per boot, and SD cards corrupt when power is cut mid-write.

### Cheap steps, for the installer

- [ ] Shutdown button: `dtoverlay=gpio-shutdown` in `config.txt` makes GPIO 3 a shutdown
  button (short to ground for a clean shutdown; the same pin wakes the Pi from halt). Needs
  a two-pin momentary switch and nothing else. Mention the pin in the customer instructions.
- [ ] Cap the journal (`SystemMaxUse=`, `RuntimeMaxUse=` in `journald.conf`) so it can never
  fill the card. Keep it persistent: the log is what a support request needs.

### Read-only root (overlay filesystem), for the image

`raspi-config nonint do_overlayfs 0` (or the "Overlay File System" entry in `raspi-config`)
puts an overlay on the root filesystem: the card is only read, every write goes to RAM and is
gone at reboot. The Pi then survives any number of power cuts.

- [ ] Only in the image (section 1), not in the installer: with the overlay on, an upgrade
  needs `raspi-config nonint do_overlayfs 1`, a reboot, the installer, and the overlay back
  on. Document that sequence next to the image.
- [ ] The boot partition must stay writable, otherwise the settings step cannot reset the
  change file and write the current file. raspi-config asks separately whether to make
  `/boot/firmware` read-only: answer no.
- [ ] The settings step writes `/etc/naneos-uploader/options.env` and the NetworkManager
  profile on the root filesystem. With the overlay those writes land in RAM and vanish at
  the next boot, so a change from the SD card would be applied for one boot only. Options:
  keep the environment file on the boot partition too (`EnvironmentFile=` can point there;
  it is world readable, but the options are not secret), and for WiFi write the profile to
  a small writable data partition or remount the root read-write for the duration of the
  settings step. Decide before building the image.
- [ ] The journal is in RAM with the overlay. Acceptable for customer Pis; for hardware
  tests use the installer without overlay.
- [ ] Persistent log and journal caps become moot with the overlay; the shutdown button
  stays useful.

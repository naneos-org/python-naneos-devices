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
- [ ] The settings files (section 2) are on the boot partition and ship with the image by
  themselves. Before capturing an image from a prepared installation: reset
  `naneos-uploader-change.txt` to its template, empty `/etc/naneos-uploader/options.env`,
  and remove the WiFi profiles of the preparation (`naneos-*.nmconnection` and the netplan
  one from the Imager), so no customer receives our network credentials.
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
- [x] WiFi: `WIFI_SSID` and `WIFI_PASSWORD` add a NetworkManager profile (root-only
  keyfile, higher autoconnect priority, known networks kept). The password is on the card
  in plain text until the boot that applies it, the same trade-off the Imager makes.
- [x] Tested on a Pi Zero 2 W (Trixie) 2026-09-21: options applied at boot, WiFi added and
  failover to the new network works. Nothing left open here.

Decided against (2026-09-21): a runtime reload of the file without reboot (card edits come
with a power cycle anyway, and over SSH a service restart applies the file), and a
`WIFI_COUNTRY` key (the Imager always does the first setup and sets the country).

---

## 3. Surviving hard power-offs: journal in RAM

Noted 2026-09-21. A headless customer Pi is switched off by pulling the plug. The
measurement data does not suffer: the uploader writes nothing to the card, unsent snapshots
live in memory (at most `MAX_PENDING_UPLOADS`, about 10 minutes) and the Partector keeps its
own record. The card does: the journal was written every interval, the two settings files on
the FAT boot partition once per boot, and SD cards corrupt when power is cut mid-write.

- [x] Journal in RAM (2026-09-21): the installer writes `Storage=volatile` with a 16 MB cap
  into `/etc/systemd/journald.conf.d/naneos-volatile.conf`. No writes to the card during
  operation; the log is lost at reboot, which is acceptable for customer Pis. For debugging,
  delete the drop-in and reboot.

Decided against (2026-09-21): the read-only root (overlay filesystem from `raspi-config`).
Too much for the gain: every upgrade would need the overlay off and on again with reboots,
and the settings step writes to the root filesystem (`options.env`, the WiFi profile), which
would then have to move to the boot partition or a data partition. With the journal in RAM
the remaining writes are rare and small: NetworkManager leases, `fake-hwclock` once an hour,
the settings files once per boot, and the swap file under memory pressure. Also dropped: a
GPIO shutdown button (`dtoverlay=gpio-shutdown`), since pulling the plug is acceptable once
nothing is written during operation.

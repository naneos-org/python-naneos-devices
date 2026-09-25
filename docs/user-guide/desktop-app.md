# Desktop App (Tray Icon)

`naneos-gui` is a small tray icon for Windows, macOS and Linux. It runs the device manager in
the background, reads every Partector in reach over USB and Bluetooth, uploads the data to the
naneos IoT service like the [Raspberry Pi uploader](raspberry-pi-setup.md), and shows which
devices it currently sees.

It starts at every login, so a computer with a Partector attached is a permanent uploader. For
an always-on box without a screen use the Raspberry Pi setup instead; this page is about
desktop computers.

## Install

The installer installs [uv](https://docs.astral.sh/uv/) if you do not have it, installs
`naneos-devices` with the tray app into its own environment, registers the app to start at
login and starts it. It changes only your user account and never asks for administrator rights.

**macOS and Linux**, in a terminal:

```bash
curl -LsSf https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install-desktop.sh | sh
```

**Windows**, in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install-desktop.ps1 | iex"
```

Options go after `sh -s --` on macOS and Linux:

```bash
curl -LsSf <url> | sh -s -- --version 2.1.0 --no-start
```

On Windows an option needs the script as a script block:

```powershell
powershell -ExecutionPolicy ByPass -c "& ([scriptblock]::Create((irm <url>))) -Version 2.1.0 -NoStart"
```

| macOS and Linux | Windows | Effect |
|---|---|---|
| `--version X.Y.Z` | `-Version X.Y.Z` | install this release instead of the latest one |
| `--pre` | `-Pre` | also consider pre-releases (release candidates) |
| `--ref BRANCH` | `-Ref BRANCH` | install straight from GitHub, to test a branch |
| `--python X.Y` | `-Python X.Y` | Python for the app (default 3.13; uv downloads it if needed) |
| `--no-autostart` | `-NoAutostart` | do not start at login |
| `--no-start` | `-NoStart` | do not start the app now |
| `--uninstall` | `-Uninstall` | stop and remove the app |

## The menu

Click the icon (menu bar on macOS, notification area on Windows, tray on Linux):

```
naneos devices 2.1.0
Upload: on · 0 pending
──────────────────────────
P2 Pro  SN8764  USB  1 s
P2      SN8617  USB  1 s
P2      SN8123  BLE  2 s
──────────────────────────
✓ Start at login
  Open log folder
  Quit
```

* The upload line shows whether the data is uploaded and how many uploads (of 30 seconds of
  data each) are waiting because there is no connection to the internet. Data that could not
  be sent is kept in memory only, the app never writes measurement data to disk, so it is lost
  when the app quits.
* Each device row shows the device type, the serial number, how it is connected (USB or BLE)
  and how long ago the last measurement arrived. `–` means connected, no data yet. A device
  reachable over both is listed as USB.
* **Start at login** switches the autostart on or off.
* **Quit** stops the app. It waits for the Bluetooth links to close and for pending data to be
  sent, which usually takes a few seconds and at most about 25 s.

Starting the app a second time does nothing but open the menu of the running one. Only one
copy can run, because two would fight over the USB ports.

The app uses the default settings of the [device manager](../index.md): USB and Bluetooth on,
one upload every 30 seconds. Choosing settings from the app is planned.

**One program per USB device.** A Partector on USB can be opened by one program at a time.
While the tray app runs, a script of your own cannot open the same device: quit the app first.

## macOS

The installer creates `~/Applications/Naneos Devices.app`. The app has to be a bundle because
macOS asks for Bluetooth access in the name of an application, and only a bundle can carry the
text of that question. The first time the app starts, macOS asks whether **Naneos Devices** may
use Bluetooth: choose **Allow**. Until you answer, USB devices work but Bluetooth ones do not,
and Quit takes the full 25 seconds.

The permission is kept when the app is updated. macOS may ask again if the installation moves
to another folder (a different uv tool folder). You can change your answer in System Settings →
Privacy & Security → Bluetooth.

Start at login is a LaunchAgent (`~/Library/LaunchAgents/org.naneos.devices.plist`). macOS
shows a "Background item added" notice once.

## Windows

Start at login is a value in `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
(no administrator rights needed), and the installer adds a Start Menu shortcut, so the app can
be started again after Quit. The app is not code-signed.

## Linux

Start at login is `~/.config/autostart/naneos-devices.desktop`, and the installer adds an
entry to the application menu.

* **Tray icon.** Desktops that support the StatusNotifier tray standard (KDE, XFCE, Cinnamon,
  Ubuntu) show the icon. Plain GNOME has no tray: install the extension *AppIndicator and
  KStatusNotifierItem Support*. Without a tray the app keeps reading and uploading, you just do
  not see it, and it says so in the log file.
* **USB permission.** A USB Partector is a serial port that only members of one group may
  open (`dialout` on Debian, Ubuntu and Fedora, `uucp` on Arch). If you are not in it, the
  installer prints the command: `sudo usermod -aG dialout $USER`, then log out and back in.
* **Qt library.** On X11 (not Wayland) Qt needs `libxcb-cursor`: `sudo apt install libxcb-cursor0`
  on Debian and Ubuntu, `sudo dnf install xcb-util-cursor` on Fedora. The installer checks and
  tells you.
* Bluetooth uses BlueZ, so `bluetoothd` has to be running (it is on all desktop distributions).

## Update and uninstall

To update run the install command again. It stops the running app, installs the newest
release, starts the app again and leaves your choice for Start at login alone.

To uninstall run the installer with `--uninstall` (`-Uninstall` on Windows). It stops the app,
switches the autostart off and removes the app. uv, the log files and your data stay. On macOS
the Bluetooth permission also stays; to forget it run
`tccutil reset BluetoothAlways org.naneos.devices`.

## Log files

The app writes `naneos-devices.log` (5 files of up to 5 MB, the oldest are dropped). **Open log
folder** in the menu opens the folder:

| | Folder |
|---|---|
| macOS | `~/Library/Logs/naneos-devices` |
| Windows | `%LOCALAPPDATA%\naneos\naneos-devices\Logs` |
| Linux | `~/.local/state/naneos-devices` |

To see the log lines live, start the app from a terminal: `naneos-gui --log-level DEBUG`.

## Command line

The installer puts the environment of the app in the folder that `uv tool dir` prints. The
app itself is the command `naneos-gui`:

```
naneos-gui                                   start the app (a second start opens the menu)
naneos-gui --quit                            stop the running app and wait for it
naneos-gui --autostart on|off|status         start at login
naneos-gui --integration install|remove      macOS app bundle / Linux application menu entry
naneos-gui --no-upload                       do not upload (for testing)
naneos-gui --log-level DEBUG                 more detail in the log
naneos-gui --version
```

`naneos-gui --version`, `--autostart` and `--integration` work without Qt. Everything else
needs the `gui` extra: `uv tool install "naneos-devices[gui]"` (or `pip install
"naneos-devices[gui]"`). The Raspberry Pi uploader does not install it.

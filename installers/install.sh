#!/usr/bin/env bash
# naneos uploader installer for Raspberry Pi OS (Bookworm or newer, Python 3.11+).
#
# Installs the naneos-devices package from PyPI into a virtual environment and runs the
# `naneos-uploader` command as a systemd service that starts on boot.
# Re-running the installer upgrades an existing installation.
#
# Usage (as root):
#   curl -fsSL https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install.sh \
#     | sudo bash -s -- [--version <version> | --pre | --ref <branch-or-tag>] [--user <name>]
#                      [--auto-update | --no-auto-update]
#
#   (default)  the newest release on PyPI
#   --version  this version from PyPI, e.g. --version 2.0.4rc1
#   --pre      the newest version on PyPI, pre-releases included
#              (2.0.4rc1 if that is newer than the last release, else the release)
#   --ref      a git branch or tag from GitHub instead of PyPI,
#              e.g. --ref release_test for hardware testing before a merge
#   --user     unprivileged user that runs the service, default: the sudo user
#   --auto-update     check once a day for a new release and install it
#   --no-auto-update  never (the default on a fresh installation; without either
#                     flag a re-run keeps the current setting)
set -euo pipefail

REPO="naneos-org/python-naneos-devices"
REF=""
PYPI_VERSION=""
PRE=""
SOURCES=0
USER_NAME="${SUDO_USER:-pi}"
SERVICE="naneos_uploader"

AUTO_UPDATE=""  # "on", "off" or "" (keep)

usage() { sed -n '2,22p' "$0" 2>/dev/null || true; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) REF="$2"; SOURCES=$((SOURCES + 1)); shift 2 ;;
    --version) PYPI_VERSION="${2#v}"; SOURCES=$((SOURCES + 1)); shift 2 ;;
    --pre) PRE="--pre"; SOURCES=$((SOURCES + 1)); shift ;;
    --user) USER_NAME="$2"; shift 2 ;;
    --auto-update) AUTO_UPDATE="on"; shift ;;
    --no-auto-update) AUTO_UPDATE="off"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

if [[ "$SOURCES" -gt 1 ]]; then
  echo "Use only one of --ref, --version and --pre."
  exit 1
fi

if [[ "$EUID" -ne 0 ]]; then
  echo "Please run the installer with root rights: sudo $0"
  exit 1
fi

HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
if [[ -z "$HOME_DIR" ]]; then
  echo "User $USER_NAME does not exist."
  exit 1
fi
APP_DIR="$HOME_DIR/naneos-uploader"
PACKAGE_URL="https://github.com/$REPO/archive/$REF.tar.gz"
if [[ -n "$REF" ]]; then
  REQUIREMENT=""
  SOURCE="GitHub $REF"
elif [[ -n "$PYPI_VERSION" ]]; then
  REQUIREMENT="naneos-devices==$PYPI_VERSION"
  SOURCE="PyPI $PYPI_VERSION"
elif [[ -n "$PRE" ]]; then
  REQUIREMENT="naneos-devices"
  SOURCE="PyPI, newest version including pre-releases"
else
  REQUIREMENT="naneos-devices"
  SOURCE="PyPI, newest release"
fi

echo ">> naneos uploader installer"
echo "   user:    $USER_NAME"
echo "   app dir: $APP_DIR"
echo "   source:  $SOURCE"
echo

# 1) System packages (no full upgrade: that is the owner's decision, not the installer's)
echo ">> Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip iw >/dev/null
# 32-bit ARM (Pi Zero W, Pi 1/2, or a 32-bit OS on newer boards): PyPI has no
# numpy wheels for it, so pip takes the ones from piwheels. Those link against
# the system OpenBLAS instead of bundling it, and numpy fails to import
# without these two packages ("libopenblas.so.0: cannot open shared object").
# The 64-bit wheels from PyPI ship their own BLAS and need nothing.
case "$(uname -m)" in
  armv6l|armv7l)
    echo ">> 32-bit ARM detected ($(uname -m)): installing OpenBLAS for the piwheels numpy build..."
    apt-get install -y -qq libopenblas0-pthread libgfortran5 >/dev/null
    ;;
esac

# 2) Virtual environment with the package from PyPI or the chosen git ref
echo ">> Installing naneos-devices ($SOURCE) into $APP_DIR/.venv ..."
mkdir -p "$APP_DIR"
chown "$USER_NAME":"$USER_NAME" "$APP_DIR"
sudo -u "$USER_NAME" bash -c "
  set -e
  cd '$APP_DIR'
  [ -d .venv ] || python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
"
if [[ -n "$REQUIREMENT" ]]; then
  # The package first, without its dependencies: --pre would otherwise let
  # pre-releases of numpy, pandas and the like in as well. The forced reinstall
  # also replaces an installation from a git ref with the same version number.
  # The second step pins what the first one chose and resolves the dependencies.
  # --no-cache-dir: look the version up without pip's local HTTP cache. It costs
  # nothing here (one small wheel) and leaves PyPI as the only source of a stale
  # answer in the minutes after an upload.
  sudo -u "$USER_NAME" bash -c "
    set -e
    cd '$APP_DIR'
    .venv/bin/pip install --quiet --no-cache-dir --force-reinstall --no-deps $PRE '$REQUIREMENT'
  "
  RESOLVED="$(sudo -u "$USER_NAME" "$APP_DIR/.venv/bin/python" -c "
from importlib.metadata import version
print(version('naneos-devices'))
")"
  sudo -u "$USER_NAME" bash -c "
    set -e
    cd '$APP_DIR'
    .venv/bin/pip install --quiet --upgrade 'naneos-devices==$RESOLVED'
  "
  PACKAGE_URL="PyPI"
else
  # Two pip steps: the first resolves and upgrades the dependencies, the second
  # replaces the package itself. pip keeps an installed package when the
  # version number is unchanged, even if the archive URL (the git ref) differs,
  # so switching between branches or a branch and master needs the forced,
  # dependency-free reinstall.
  sudo -u "$USER_NAME" bash -c "
    set -e
    cd '$APP_DIR'
    .venv/bin/pip install --quiet --upgrade '$PACKAGE_URL'
    .venv/bin/pip install --quiet --force-reinstall --no-deps '$PACKAGE_URL'
  "
fi
VERSION="$("$APP_DIR/.venv/bin/naneos-uploader" --version)"
INSTALLED_FROM="$("$APP_DIR/.venv/bin/python" -c "
import json
from importlib.metadata import distribution
text = distribution('naneos-devices').read_text('direct_url.json') or '{}'
print(json.loads(text).get('url', 'PyPI'))
")"
if [[ "$INSTALLED_FROM" != "$PACKAGE_URL" ]]; then
  echo "!! Installed from $INSTALLED_FROM, expected $PACKAGE_URL"
  exit 1
fi
echo "   installed: $VERSION from $INSTALLED_FROM"

# 3) Settings from the SD card. naneos-uploader-settings (part of the package)
# reads naneos-uploader-change.txt on the boot partition, validates the OPTIONS
# line, stores it in an environment file the service expands in ExecStart, adds
# a WiFi network from WIFI_SSID/WIFI_PASSWORD as a NetworkManager profile, and
# writes naneos-uploader-current.txt. A oneshot unit runs it before the service
# at every boot, and the service pulls it in (Wants=) on a manual restart too.
# It runs after NetworkManager so that `nmcli connection reload` reaches it.
# The environment file survives upgrades: the installer never touches it.
BOOT_DIR=/boot/firmware
[[ -d "$BOOT_DIR" ]] || BOOT_DIR=/boot
ENV_FILE=/etc/naneos-uploader/options.env
SETTINGS_CMD="$APP_DIR/.venv/bin/naneos-uploader-settings"
SETTINGS_SERVICE="${SERVICE}_settings"
if [[ -x "$SETTINGS_CMD" ]]; then
  echo ">> Writing /etc/systemd/system/$SETTINGS_SERVICE.service ..."
  cat > "/etc/systemd/system/$SETTINGS_SERVICE.service" <<UNIT
[Unit]
Description=naneos uploader settings from the SD card ($BOOT_DIR/naneos-uploader-change.txt)
RequiresMountsFor=$BOOT_DIR
After=NetworkManager.service
Before=$SERVICE.service

[Service]
Type=oneshot
ExecStart=$SETTINGS_CMD --boot-dir $BOOT_DIR --env-file $ENV_FILE
UNIT
  chmod 644 "/etc/systemd/system/$SETTINGS_SERVICE.service"
  SETTINGS_UNIT="$SETTINGS_SERVICE.service"
else
  # An older package without the command (--version, --ref): plain service.
  rm -f "/etc/systemd/system/$SETTINGS_SERVICE.service"
  SETTINGS_UNIT=""
fi

# systemd service running the naneos-uploader command
echo ">> Writing /etc/systemd/system/$SERVICE.service ..."
cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=naneos uploader (Partector data to the naneos IoT service)
After=network-online.target bluetooth.target $SETTINGS_UNIT
Wants=network-online.target $SETTINGS_UNIT

[Service]
EnvironmentFile=-$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/naneos-uploader \$NANEOS_UPLOADER_OPTIONS
WorkingDirectory=$APP_DIR
Restart=always
RestartSec=5
User=$USER_NAME

[Install]
WantedBy=multi-user.target
UNIT
chmod 644 "/etc/systemd/system/$SERVICE.service"

if [[ -n "$SETTINGS_UNIT" ]]; then
  echo ">> Applying settings from $BOOT_DIR/naneos-uploader-change.txt ..."
  "$SETTINGS_CMD" --boot-dir "$BOOT_DIR" --env-file "$ENV_FILE" | sed 's/^/   /'
fi

# 4) Bluetooth on, with BlueZ experimental features. Passive scanning (no scan
# requests on the antenna the Pi shares with WiFi) is only offered by
# bluetoothd when it runs with --experimental. Without it the uploader falls
# back to active scanning and says so in the log.
echo ">> Ensuring Bluetooth is enabled (bluetoothd --experimental)..."
mkdir -p /etc/systemd/system/bluetooth.service.d
cat > /etc/systemd/system/bluetooth.service.d/experimental.conf <<'CONF'
# Installed by the naneos uploader installer: passive BLE scanning needs this.
[Service]
ExecStart=
ExecStart=/usr/libexec/bluetooth/bluetoothd --experimental
CONF

# BlueZ gives up a BLE link after 420 ms without a packet. On a Pi whose WiFi
# and BLE share one antenna a single WiFi burst is longer than that, and the
# links drop every few seconds ("Connection Timeout" in btmon). The kernel
# keeps the old value for devices it already knows, so on an existing
# installation the 5 s only take effect after a reboot.
BT_CONF=/etc/bluetooth/main.conf
SUPERVISION_TIMEOUT=500 # in units of 10 ms
if [[ -f "$BT_CONF" ]] && ! grep -qE "^ConnectionSupervisionTimeout *= *$SUPERVISION_TIMEOUT\$" "$BT_CONF"; then
  echo ">> Setting the BLE supervision timeout to 5 s..."
  if grep -qE '^ConnectionSupervisionTimeout' "$BT_CONF"; then
    sed -i -E "s/^ConnectionSupervisionTimeout.*/ConnectionSupervisionTimeout=$SUPERVISION_TIMEOUT/" "$BT_CONF"
  elif grep -qE '^\[LE\]' "$BT_CONF"; then
    sed -i "/^\[LE\]/a ConnectionSupervisionTimeout=$SUPERVISION_TIMEOUT" "$BT_CONF"
  else
    printf '\n[LE]\nConnectionSupervisionTimeout=%s\n' "$SUPERVISION_TIMEOUT" >> "$BT_CONF"
  fi
  REBOOT_RECOMMENDED=1
fi
systemctl daemon-reload
systemctl restart bluetooth.service || true
rfkill unblock bluetooth || true
echo -e 'power on\nquit' | bluetoothctl >/dev/null 2>&1 || true

# 5) WiFi power save off. The brcmfmac chip on a Raspberry Pi Zero 2 W parks
# the WiFi link when idle. That stalls uploads, and because WiFi and BLE share
# one antenna it also costs BLE airtime. `iw` alone does not survive a reboot.
echo ">> Disabling WiFi power save..."
WIFI_DEV="$(iw dev 2>/dev/null | awk '/Interface/{print $2; exit}')"
if systemctl is-active --quiet NetworkManager; then
  mkdir -p /etc/NetworkManager/conf.d
  cat > /etc/NetworkManager/conf.d/wifi-powersave-off.conf <<'CONF'
# Installed by the naneos uploader installer. 2 = disable WiFi power save.
[connection]
wifi.powersave = 2
CONF
  systemctl reload NetworkManager || true
else
  cat > /etc/systemd/system/wifi-powersave-off.service <<SVC
[Unit]
Description=Disable WiFi power save
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/iw dev ${WIFI_DEV:-wlan0} set power_save off

[Install]
WantedBy=multi-user.target
SVC
  systemctl daemon-reload
  systemctl enable --now wifi-powersave-off.service || true
fi
if [[ -n "$WIFI_DEV" ]]; then
  iw dev "$WIFI_DEV" set power_save off || true
  echo "   $WIFI_DEV: $(iw dev "$WIFI_DEV" get power_save 2>/dev/null || echo 'state unknown')"
fi

# 6) Journal in RAM. The service logs a few lines every interval, and that
# was the only write to the SD card during operation. Customer Pis are
# switched off by pulling the plug, and SD cards corrupt when that happens
# mid-write. The log is lost at reboot (journalctl shows the current boot);
# for persistent logs while debugging, delete the drop-in and reboot.
echo ">> Keeping the journal in RAM (no log writes to the SD card)..."
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/naneos-volatile.conf <<'CONF'
# Installed by the naneos uploader installer: the journal stays in RAM so the
# SD card is not written every upload interval. Delete this file and reboot
# for a persistent journal.
[Journal]
Storage=volatile
RuntimeMaxUse=16M
CONF
systemctl restart systemd-journald || true

# 7) Automatic updates. naneos-uploader-update (part of the package) asks PyPI
# for the newest release once a day and, only if it is newer than the installed
# one, downloads the installer of that release and runs it. The timer is the
# single switch: --auto-update / --no-auto-update here, AUTO_UPDATE=on|off in
# the change file on the SD card, or systemctl enable/disable --now.
UPDATE_CMD="$APP_DIR/.venv/bin/naneos-uploader-update"
UPDATE_SERVICE="${SERVICE}_update"
if [[ -x "$UPDATE_CMD" ]]; then
  echo ">> Writing /etc/systemd/system/$UPDATE_SERVICE.service and .timer ..."
  cat > "/etc/systemd/system/$UPDATE_SERVICE.service" <<UNIT
[Unit]
Description=naneos uploader: update to the newest release if there is one
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$UPDATE_CMD --user $USER_NAME
UNIT
  cat > "/etc/systemd/system/$UPDATE_SERVICE.timer" <<UNIT
[Unit]
Description=naneos uploader: check for a new release once a day

[Timer]
OnCalendar=*-*-* 03:00:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
UNIT
  chmod 644 "/etc/systemd/system/$UPDATE_SERVICE.service" "/etc/systemd/system/$UPDATE_SERVICE.timer"
  systemctl daemon-reload
  if [[ -z "$AUTO_UPDATE" ]]; then
    systemctl is-enabled --quiet "$UPDATE_SERVICE.timer" 2>/dev/null && AUTO_UPDATE="on" || AUTO_UPDATE="off"
  fi
  if [[ "$AUTO_UPDATE" == "on" ]]; then
    systemctl enable --now "$UPDATE_SERVICE.timer" >/dev/null 2>&1
  else
    systemctl disable --now "$UPDATE_SERVICE.timer" >/dev/null 2>&1 || true
  fi
else
  # An older package without the command (--version, --ref): no timer.
  systemctl disable --now "$UPDATE_SERVICE.timer" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/$UPDATE_SERVICE.service" "/etc/systemd/system/$UPDATE_SERVICE.timer"
  AUTO_UPDATE="unavailable"
fi

# 8) Enable and (re)start the service
echo ">> Starting the service..."
systemctl daemon-reload
systemctl enable "$SERVICE.service" >/dev/null
systemctl restart "$SERVICE.service"

echo
echo ">> Done: $VERSION runs as $SERVICE.service"
echo "   logs:    journalctl -u $SERVICE.service -f  (in RAM, current boot only)"
if [[ -n "$SETTINGS_UNIT" ]]; then
  echo "   options: edit $BOOT_DIR/naneos-uploader-change.txt (options, WiFi, AUTO_UPDATE; applied at boot),"
  echo "            see naneos-uploader-current.txt"
fi
case "$AUTO_UPDATE" in
  on)  echo "   updates: automatic, once a day (off: --no-auto-update or AUTO_UPDATE=off on the card)" ;;
  off) echo "   updates: off (on: --auto-update or AUTO_UPDATE=on on the card)" ;;
esac
echo "   upgrade: re-run this installer (optionally with --version, --pre or --ref)"
if [[ -n "${REBOOT_RECOMMENDED:-}" ]]; then
  echo "   reboot:  the new BLE supervision timeout needs one (sudo reboot)"
fi

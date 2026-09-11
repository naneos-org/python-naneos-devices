#!/usr/bin/env bash
# naneos uploader installer for Raspberry Pi OS (Bookworm or newer, Python 3.11+).
#
# Installs the naneos-devices package into a virtual environment and runs the
# `naneos-uploader` command as a systemd service that starts on boot.
# Re-running the installer upgrades an existing installation.
#
# Usage (as root):
#   curl -fsSL https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install.sh \
#     | sudo bash -s -- [--ref <branch-or-tag>] [--user <name>]
#
#   --ref   git branch or tag to install, default: master
#           e.g. --ref release_test for hardware testing, --ref v1.2.0 for a release
#   --user  unprivileged user that runs the service, default: the sudo user
set -euo pipefail

REPO="naneos-org/python-naneos-devices"
REF="master"
USER_NAME="${SUDO_USER:-pi}"
SERVICE="naneos_uploader"

usage() { sed -n '2,15p' "$0" 2>/dev/null || true; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) REF="$2"; shift 2 ;;
    --user) USER_NAME="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

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

echo ">> naneos uploader installer"
echo "   user:    $USER_NAME"
echo "   app dir: $APP_DIR"
echo "   ref:     $REF"
echo

# 1) System packages (no full upgrade: that is the owner's decision, not the installer's)
echo ">> Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip iw >/dev/null

# 2) Virtual environment with the package from the chosen git ref
echo ">> Installing naneos-devices ($REF) into $APP_DIR/.venv ..."
mkdir -p "$APP_DIR"
chown "$USER_NAME":"$USER_NAME" "$APP_DIR"
sudo -u "$USER_NAME" bash -c "
  set -e
  cd '$APP_DIR'
  [ -d .venv ] || python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet --upgrade '$PACKAGE_URL'
"
VERSION="$("$APP_DIR/.venv/bin/naneos-uploader" --version)"
echo "   installed: $VERSION"

# 3) systemd service running the naneos-uploader command
echo ">> Writing /etc/systemd/system/$SERVICE.service ..."
cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=naneos uploader (Partector data to the naneos IoT service)
After=network-online.target bluetooth.target
Wants=network-online.target

[Service]
ExecStart=$APP_DIR/.venv/bin/naneos-uploader
WorkingDirectory=$APP_DIR
Restart=always
RestartSec=5
User=$USER_NAME

[Install]
WantedBy=multi-user.target
UNIT
chmod 644 "/etc/systemd/system/$SERVICE.service"

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

# 6) Enable and (re)start the service
echo ">> Starting the service..."
systemctl daemon-reload
systemctl enable "$SERVICE.service" >/dev/null
systemctl restart "$SERVICE.service"

echo
echo ">> Done: $VERSION runs as $SERVICE.service"
echo "   logs:    journalctl -u $SERVICE.service -f"
echo "   upgrade: re-run this installer (optionally with another --ref)"

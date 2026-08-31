#!/usr/bin/env bash
set -euo pipefail

echo ">> Naneos Uploader Installer"

# 1) check root rights
if [[ "$EUID" -ne 0 ]]; then
  echo "Please run installer with root rights: sudo $0"
  exit 1
fi

# 2) Determine user & paths
USER_NAME="${SUDO_USER:-pi}"
HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
APP_DIR="$HOME_DIR/naneos-uploader"

# Directory of the script (Repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "   Installing for User: $USER_NAME"
echo "   Home:   $HOME_DIR"
echo "   AppDir: $APP_DIR"
echo

# 3) Prepare system
echo ">> Updating system..."
apt update
apt -y full-upgrade
apt -y autoremove

echo ">> Installing Python & venv..."
apt -y install python3-full python3-pip python3-venv

# `iw` is used below to turn WiFi power save off.
apt -y install iw

# 4) Create app directory and copy files
echo ">> Creating app directory and copying files..."
mkdir -p "$APP_DIR"
chown -R "$USER_NAME":"$USER_NAME" "$APP_DIR"

# Copy Python script & requirements
cp "$SCRIPT_DIR/uploader-script.py" "$APP_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$APP_DIR/"

chown "$USER_NAME":"$USER_NAME" "$APP_DIR/uploader-script.py" "$APP_DIR/requirements.txt"
chmod +x "$APP_DIR/uploader-script.py"

# 5) Create virtual environment and install dependencies
echo ">> Creating virtual environment and installing Python packages..."
sudo -u "$USER_NAME" bash -c "
  cd '$APP_DIR'
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
"

# 6) Create systemd service from template
echo ">> Creating systemd service file..."
TEMPLATE="$SCRIPT_DIR/naneos_uploader.service"
SERVICE_FILE="/etc/systemd/system/naneos_uploader.service"

sed \
  -e "s|{{APP_DIR}}|$APP_DIR|g" \
  -e "s|{{USER_NAME}}|$USER_NAME|g" \
  "$TEMPLATE" > "$SERVICE_FILE"

chmod 644 "$SERVICE_FILE"

# 7) Fix Bluetooth state on Raspberry Pi
echo ">> Ensuring Bluetooth is enabled..."
rfkill unblock bluetooth || true

# Try to power on BT controller non-interactively
echo -e 'power on\nquit' | bluetoothctl >/dev/null 2>&1 || true

# 8) Disable WiFi power save
# The brcmfmac chip on a Raspberry Pi Zero 2 W parks the WiFi link when idle.
# That stalls uploads, and because WiFi and BLE share one antenna it also costs
# BLE airtime. `iw` alone does not survive a reboot, so make it persistent too.
echo ">> Disabling WiFi power save..."
WIFI_DEV="$(iw dev 2>/dev/null | awk '/Interface/{print $2; exit}')"

if systemctl is-active --quiet NetworkManager; then
  # NetworkManager re-applies its own setting on every (re)connect, so a config
  # drop-in is the only thing that sticks. 2 = disable.
  mkdir -p /etc/NetworkManager/conf.d
  cat > /etc/NetworkManager/conf.d/wifi-powersave-off.conf <<'EOF'
# Installed by the naneos uploader installer.
# 2 = disable WiFi power save; the Pi Zero 2 W otherwise sleeps the link when
# idle, which stalls uploads and costs BLE airtime on the shared antenna.
[connection]
wifi.powersave = 2
EOF
  systemctl reload NetworkManager || true
  echo "   Installed /etc/NetworkManager/conf.d/wifi-powersave-off.conf"
else
  # No NetworkManager (older Raspberry Pi OS images): re-apply it at every boot.
  cat > /etc/systemd/system/wifi-powersave-off.service <<EOF
[Unit]
Description=Disable WiFi power save
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/iw dev ${WIFI_DEV:-wlan0} set power_save off

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now wifi-powersave-off.service || true
  echo "   Installed wifi-powersave-off.service"
fi

# Apply to the running link as well, so no reboot is needed.
if [[ -n "$WIFI_DEV" ]]; then
  iw dev "$WIFI_DEV" set power_save off || true
  echo "   $WIFI_DEV: $(iw dev "$WIFI_DEV" get power_save 2>/dev/null || echo 'state unknown')"
fi

# 9) Enable & start service
echo ">> Reloading systemd, enabling & starting service..."
systemctl daemon-reload
systemctl enable naneos_uploader.service
systemctl start naneos_uploader.service

echo
echo ">> Installation completed."
echo "Status:"
systemctl status naneos_uploader.service --no-pager || true
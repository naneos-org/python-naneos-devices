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

# 8) Enable & start service
echo ">> Reloading systemd, enabling & starting service..."
systemctl daemon-reload
systemctl enable naneos_uploader.service
systemctl start naneos_uploader.service

echo
echo ">> Installation completed."
echo "Status:"
systemctl status naneos_uploader.service --no-pager || true
#!/bin/sh
# Install the naneos tray app on macOS or Linux (the desktop app, not the Raspberry Pi
# uploader: that one has its own installer, install.sh).
#
#   curl -LsSf https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install-desktop.sh | sh
#
# It installs uv if you do not have it, installs the naneos-devices package with the
# tray app into its own environment, and starts the app at every login. Run it again to
# update: it stops the running app, installs the new version and starts it again.
#
# Options (put them after `sh -s --`):
#   --version X.Y.Z    install this release instead of the latest one
#   --pre              also consider pre-releases (release candidates)
#   --ref BRANCH|TAG   install straight from GitHub (for testing a branch)
#   --python X.Y       Python for the app (default: 3.13, uv downloads it if needed)
#   --no-autostart     do not start the app at login
#   --no-start         do not start the app now
#   --uninstall        stop the app and remove it (uv and the log files stay)
#   -h, --help         this text
#
# Example: curl -LsSf <url> | sh -s -- --version 2.1.0 --no-start
#
# For developers: NANEOS_REQUIREMENT="naneos-devices[gui] @ file:///path/to/checkout" installs
# that instead of a release.
#
# Changes only your home directory. Never uses sudo.

set -eu

REPO="naneos-org/python-naneos-devices"
PACKAGE="naneos-devices"

VERSION="${NANEOS_VERSION:-}"
REF="${NANEOS_REF:-}"
PYTHON_VERSION="${NANEOS_PYTHON:-3.13}"
PRE=0
AUTOSTART=1
START=1
UNINSTALL=0

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Install the naneos tray app on macOS or Linux.

  curl -LsSf https://raw.githubusercontent.com/naneos-org/python-naneos-devices/master/installers/install-desktop.sh | sh

Options (put them after `sh -s --`):
  --version X.Y.Z    install this release instead of the latest one
  --pre              also consider pre-releases (release candidates)
  --ref BRANCH|TAG   install straight from GitHub (for testing a branch)
  --python X.Y       Python for the app (default: 3.13, uv downloads it if needed)
  --no-autostart     do not start the app at login
  --no-start         do not start the app now
  --uninstall        stop the app and remove it (uv and the log files stay)
  -h, --help         this text
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --version)
            [ $# -ge 2 ] || die "--version needs a value"
            VERSION="$2"
            shift
            ;;
        --pre) PRE=1 ;;
        --ref)
            [ $# -ge 2 ] || die "--ref needs a value"
            REF="$2"
            shift
            ;;
        --python)
            [ $# -ge 2 ] || die "--python needs a value"
            PYTHON_VERSION="$2"
            shift
            ;;
        --no-autostart) AUTOSTART=0 ;;
        --no-start) START=0 ;;
        --uninstall) UNINSTALL=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        *) die "unknown option: $1 (see --help)" ;;
    esac
    shift
done

[ -z "$VERSION" ] || [ -z "$REF" ] || die "use either --version or --ref, not both"

[ "$(id -u)" -ne 0 ] || die "do not run this as root: the app belongs to your user account"

case "$(uname -s)" in
    Darwin) OS=macos ;;
    Linux) OS=linux ;;
    *) die "this installer is for macOS and Linux; on Windows use install-desktop.ps1" ;;
esac

if [ "$OS" = macos ]; then
    APP_BUNDLE="$HOME/Applications/Naneos Devices.app"
    LOG_DIR="$HOME/Library/Logs/naneos-devices"
else
    LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/naneos-devices"
fi

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return 0
    fi
    # A fresh uv is not on the PATH of this shell yet; look where its installer puts it.
    for dir in "${UV_INSTALL_DIR:-}" "${XDG_BIN_HOME:-}" "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        if [ -n "$dir" ] && [ -x "$dir/uv" ]; then
            printf '%s\n' "$dir/uv"
            return 0
        fi
    done
    return 1
}

# Ask the running tray app to quit and wait for it, from the tool environment's python
# (synchronous, unlike the naneos-gui launcher).
stop_running_app() {
    if [ -x "$TOOL_PY" ]; then
        "$TOOL_PY" -m naneos.gui --quit --timeout 30 </dev/null || true
    fi
    # An app that did not answer, or one too old to know --quit.
    pkill -f "$TOOL_ROOT/.*naneos[-.]gui" >/dev/null 2>&1 || true
}

uninstall() {
    say "Removing the naneos tray app ..."
    if UV=$(find_uv); then
        TOOL_ROOT="$("$UV" tool dir </dev/null)/$PACKAGE"
        TOOL_PY="$TOOL_ROOT/bin/python"
        stop_running_app
        if [ -x "$TOOL_PY" ]; then
            "$TOOL_PY" -m naneos.gui --autostart off </dev/null || true
            "$TOOL_PY" -m naneos.gui --integration remove </dev/null || true
        fi
        "$UV" tool uninstall "$PACKAGE" </dev/null || true
    fi
    # What the app writes, in case its environment is already gone.
    if [ "$OS" = macos ]; then
        rm -rf "$APP_BUNDLE" "$HOME/Library/LaunchAgents/org.naneos.devices.plist"
    else
        rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/naneos-devices.desktop" \
            "${XDG_DATA_HOME:-$HOME/.local/share}/applications/naneos-devices.desktop"
    fi
    say "Removed. uv, the log files in $LOG_DIR and your data stay."
    if [ "$OS" = macos ]; then
        say "To also forget the Bluetooth permission: tccutil reset BluetoothAlways org.naneos.devices"
    fi
}

linux_hints() {
    # Qt on X11 needs libxcb-cursor. Wayland sessions do not.
    if [ "${XDG_SESSION_TYPE:-}" != wayland ]; then
        LDCONFIG=$(command -v ldconfig || true)
        [ -n "$LDCONFIG" ] || LDCONFIG=/sbin/ldconfig
        if [ -x "$LDCONFIG" ] && ! "$LDCONFIG" -p 2>/dev/null | grep -q 'libxcb-cursor\.so\.0'; then
            warn "the tray app needs the library libxcb-cursor on X11. Install it with one of:"
            warn "  sudo apt install libxcb-cursor0        (Debian, Ubuntu)"
            warn "  sudo dnf install xcb-util-cursor       (Fedora)"
            warn "  sudo pacman -S xcb-util-cursor         (Arch)"
        fi
    fi

    # A USB Partector is a serial port; on most distributions only one group may open it.
    group=""
    for device in /dev/ttyACM0 /dev/ttyUSB0; do
        if [ -e "$device" ]; then
            group=$(stat -c %G "$device" 2>/dev/null || true)
            break
        fi
    done
    if [ -z "$group" ]; then
        if getent group dialout >/dev/null 2>&1; then
            group=dialout
        elif getent group uucp >/dev/null 2>&1; then
            group="uucp"
        fi
    fi
    if [ -n "$group" ] && [ "$group" != root ] && ! id -nG | tr ' ' '\n' | grep -qx "$group"; then
        warn "you are not in the group '$group', so a Partector on USB cannot be opened. Run:"
        warn "  sudo usermod -aG $group $USER"
        warn "then log out and back in."
    fi

    # GNOME has no tray of its own.
    case "${XDG_CURRENT_DESKTOP:-}" in
        *GNOME*)
            if command -v gdbus >/dev/null 2>&1 &&
                ! gdbus call --session --dest org.freedesktop.DBus \
                    --object-path /org/freedesktop/DBus \
                    --method org.freedesktop.DBus.NameHasOwner org.kde.StatusNotifierWatcher \
                    2>/dev/null | grep -q true; then
                warn "GNOME shows tray icons only with the extension 'AppIndicator and"
                warn "KStatusNotifierItem Support'. Without it the app still reads and uploads"
                warn "your devices, but you will not see an icon."
            fi
            ;;
    esac
}

if [ "$UNINSTALL" -eq 1 ]; then
    uninstall
    exit 0
fi

command -v curl >/dev/null 2>&1 || die "curl is needed to download uv"

if ! UV=$(find_uv); then
    say "Installing uv ..."
    UV_INSTALLER=$(mktemp)
    curl -LsSf https://astral.sh/uv/install.sh -o "$UV_INSTALLER" || die "cannot download the uv installer"
    sh "$UV_INSTALLER" </dev/null
    rm -f "$UV_INSTALLER"
    UV=$(find_uv) || die "uv was installed but I cannot find it; open a new terminal and run this again"
fi
say "Using $UV"

TOOL_ROOT="$("$UV" tool dir </dev/null)/$PACKAGE"
TOOL_PY="$TOOL_ROOT/bin/python"

# Was start at login switched off by the user? An update must not turn it back on.
KEEP_AUTOSTART_OFF=0
if [ -x "$TOOL_PY" ]; then
    status=$("$TOOL_PY" -m naneos.gui --autostart status </dev/null 2>/dev/null || true)
    case "$status" in
        *": off"*) KEEP_AUTOSTART_OFF=1 ;;
    esac
fi

stop_running_app

if [ -n "${NANEOS_REQUIREMENT:-}" ]; then
    REQUIREMENT="$NANEOS_REQUIREMENT"
elif [ -n "$VERSION" ]; then
    REQUIREMENT="${PACKAGE}[gui]==$VERSION"
elif [ -n "$REF" ]; then
    REQUIREMENT="${PACKAGE}[gui] @ https://github.com/$REPO/archive/$REF.tar.gz"
else
    REQUIREMENT="${PACKAGE}[gui]"
fi

say "Installing $REQUIREMENT (Python $PYTHON_VERSION) ..."
set -- tool install --force --python "$PYTHON_VERSION"
if [ "$PRE" -eq 1 ]; then
    set -- "$@" --prerelease allow
fi
"$UV" "$@" "$REQUIREMENT" </dev/null

[ -x "$TOOL_PY" ] || die "the installation finished but $TOOL_PY does not exist"

# An old release installs without an error: uv only warns that it has no extra "gui". The tray
# app first ships in 2.1.0, so say what is wrong instead of failing on the next command.
if ! "$TOOL_PY" -c 'import naneos.gui.app' </dev/null >/dev/null 2>&1; then
    INSTALLED=$("$TOOL_PY" -c 'import importlib.metadata as m; print(m.version("naneos-devices"))' </dev/null 2>/dev/null || echo "?")
    die "the installed $PACKAGE $INSTALLED does not contain the tray app (it first ships in 2.1.0). Either that release is not published yet, or --version is too old. To install a branch from GitHub instead, use --ref BRANCH."
fi

"$TOOL_PY" -m naneos.gui --integration install </dev/null
if [ "$AUTOSTART" -eq 1 ] && [ "$KEEP_AUTOSTART_OFF" -eq 0 ]; then
    "$TOOL_PY" -m naneos.gui --autostart on </dev/null
fi

if [ "$OS" = linux ]; then
    linux_hints
fi

if [ "$START" -eq 1 ]; then
    if [ "$OS" = macos ]; then
        open "$APP_BUNDLE"
        say "Starting the app. The first time, macOS asks whether Naneos Devices may use"
        say "Bluetooth: choose Allow."
    elif [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        if command -v setsid >/dev/null 2>&1; then
            setsid -f "$TOOL_ROOT/bin/naneos-gui" >/dev/null 2>&1 </dev/null || true
        else
            nohup "$TOOL_ROOT/bin/naneos-gui" >/dev/null 2>&1 </dev/null &
        fi
    else
        say "No desktop session here: the app starts at your next login."
    fi
fi

say ""
say "$("$TOOL_PY" -m naneos.gui --version </dev/null) is installed."
say "  Log files:  $LOG_DIR"
say "  Update:     run the same command again"
say "  Uninstall:  curl -LsSf https://raw.githubusercontent.com/$REPO/master/installers/install-desktop.sh | sh -s -- --uninstall"

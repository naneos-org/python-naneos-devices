#!/bin/sh
# Build src/naneos/gui/resources/macos/naneos-launcher (universal2, ad-hoc signed).
#
# Commit the result and do NOT rebuild it for a small change: macOS ties the
# Bluetooth permission to the code signature, so every new binary makes every
# user see the permission prompt again. After a real change, bump
# LAUNCHER_VERSION in src/naneos/gui/integration.py.
#
# Needs the Xcode command line tools (clang, lipo, codesign). Run on a Mac.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
dir="$here/../src/naneos/gui/resources/macos"
out="$dir/naneos-launcher"

clang -O2 -Wall -Wextra -mmacosx-version-min=12.0 -arch arm64 -arch x86_64 \
    -o "$out" "$dir/launcher.c"
codesign --force --sign - --identifier org.naneos.devices.launcher "$out"
codesign --verify --verbose=1 "$out"
lipo -info "$out"

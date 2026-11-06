#!/bin/sh
# Builds macos/build/HistoryLocation.app. Start it with: open macos/build/HistoryLocation.app
set -eu
cd "$(dirname "$0")"
app=build/HistoryLocation.app
rm -rf "$app"
mkdir -p "$app/Contents/MacOS"
cp HistoryLocation/Info.plist "$app/Contents/"
swiftc -O HistoryLocation/main.swift -o "$app/Contents/MacOS/HistoryLocation"
codesign --force --sign - "$app"
echo "built macos/$app"

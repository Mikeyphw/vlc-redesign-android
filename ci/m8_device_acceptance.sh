#!/usr/bin/env bash
set -Eeuo pipefail
# Capture actual screenshots and frame information without claiming a passed acceptance gate.
# Run on a desktop/host with adb; screenshots are taken from the current device screen.
: "${M8_ANDROID_PACKAGE:=com.mikeyphw.vlcredesign.debug}"
: "${M8_EVIDENCE_DIR:=$PWD/m8-device-evidence}"
command -v adb
command -v date
mkdir -p "$M8_EVIDENCE_DIR"
printf 'M8_DEVICE package=%s output=%s\n' "$M8_ANDROID_PACKAGE" "$M8_EVIDENCE_DIR"
adb devices -l
printf 'M8_DEVICE Android version:\n'
adb shell getprop ro.build.version.release
printf 'M8_DEVICE SDK:\n'
adb shell getprop ro.build.version.sdk
printf 'M8_DEVICE Physical / emulator fingerprint:\n'
adb shell getprop ro.build.fingerprint
printf 'M8_DEVICE baseline gfxinfo before screenshot:\n'
adb shell dumpsys gfxinfo "$M8_ANDROID_PACKAGE" > "$M8_EVIDENCE_DIR/gfxinfo.txt"
cat "$M8_EVIDENCE_DIR/gfxinfo.txt"
for screen in home videos search mini_player video_player; do
  printf '\nM8_DEVICE: navigate to %s on the device, then press Enter to capture it. Ctrl-C cancels.\n' "$screen"
  IFS= read -r _
  adb exec-out screencap -p > "$M8_EVIDENCE_DIR/$screen.png"
  file "$M8_EVIDENCE_DIR/$screen.png"
done
printf 'M8_DEVICE_SCREENSHOTS_CAPTURED only; no visual/performance PASS claimed\n'

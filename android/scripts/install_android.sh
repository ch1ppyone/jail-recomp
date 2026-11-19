#!/usr/bin/env bash
# Install the debug APK and stream the runtime inputs into the app's data directory.
#
#   scripts/install_android.sh
#   APP0_DIR=/path/to/app0 GAME_LANG=jp scripts/install_android.sh
#
# Layout (app-private internal storage; the Activity's baseDir() is getFilesDir()):
#   /data/user/0/dev.ch1ppy.jail/files/jail/game.img
#   /data/user/0/dev.ch1ppy.jail/files/jail/libc.img, libgxm_es4.img, libgpu_es4.img,
#                                             libfios2.img, libpvf.img, libult.img, libSceFt2.img
#   /data/user/0/dev.ch1ppy.jail/files/fs/app0/...
#
# The APK already bundles these module images and game.img. This script re-copies them
# over ADB for development, together with an already decrypted app0, so a local test
# skips the on-device PKG preparation.
#
# `run-as` works because the app is debuggable; the streams avoid a second copy in /data/local/tmp.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/android_env.sh"

PKG=dev.ch1ppy.jail
MAIN_ACTIVITY=.MainActivity
NATIV_ROOT="${NATIV_ROOT:-$ROOT/../nativ}"
GAME_RECOMP_DIR="${GAME_RECOMP_DIR:-$NATIV_ROOT/dump/decrypted/PCSG00615/recomp}"
APP0_DIR="${APP0_DIR:-$NATIV_ROOT/dump/decrypted/PCSG00615/app0}"
GAME_LANG="${GAME_LANG:-en_us}"
APK="$ROOT/app/build/outputs/apk/debug/app-debug.apk"

MODULES=(libc libgxm_es4 libgpu_es4 libfios2 libpvf libult libSceFt2)

if [ ! -x "$ANDROID_ADB" ]; then
    echo "adb not found at $ANDROID_ADB" >&2
    exit 1
fi
if [ ! -f "$APK" ]; then
    echo "APK not built: $APK (run scripts/build_android.sh)" >&2
    exit 1
fi
if [ ! -f "$GAME_RECOMP_DIR/game.img" ]; then
    echo "game.img not found: $GAME_RECOMP_DIR/game.img" >&2
    exit 1
fi
for m in "${MODULES[@]}"; do
    if [ ! -f "$GAME_RECOMP_DIR/$m.img" ]; then
        echo "module image not found: $GAME_RECOMP_DIR/$m.img" >&2
        exit 1
    fi
done

"$ANDROID_ADB" get-state >/dev/null
"$ANDROID_ADB" install -r "$APK"

"$ANDROID_ADB" shell run-as "$PKG" mkdir -p files/jail files/fs/app0
"$ANDROID_ADB" shell run-as "$PKG" mkdir -p files/shader_cache

stream_file() {   # <local file> <path inside the app's data dir>
    "$ANDROID_ADB" shell "run-as $PKG sh -c 'cat > $2'" < "$1"
}

echo "Installing game.img..."
stream_file "$GAME_RECOMP_DIR/game.img" files/jail/game.img
for m in "${MODULES[@]}"; do
    echo "Installing $m.img..."
    stream_file "$GAME_RECOMP_DIR/$m.img" "files/jail/$m.img"
done

if "$ANDROID_ADB" shell "run-as $PKG ls files/fs/app0/resource.dat" >/dev/null 2>&1; then
    echo "app0 already on device"
else
    if [ ! -d "$APP0_DIR" ]; then
        echo "app0 tree not found: $APP0_DIR" >&2
        exit 1
    fi
    echo "Streaming app0 (about 1.1 GB)..."
    ( cd "$APP0_DIR" && tar cf - . ) | "$ANDROID_ADB" shell "run-as $PKG sh -c 'tar xf - -C files/fs/app0'"
fi

"$ANDROID_ADB" shell am force-stop "$PKG" 2>/dev/null || true
"$ANDROID_ADB" shell am start -n "$PKG/$MAIN_ACTIVITY" --es lang "$GAME_LANG"

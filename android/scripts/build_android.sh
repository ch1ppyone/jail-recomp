#!/usr/bin/env bash
# Build the Android APK end to end: SDL3, optional FFmpeg, native libmain.so, then Gradle.
#
#   scripts/build_android.sh                 # with FFmpeg (movies decode)
#   scripts/build_android.sh --no-ffmpeg     # faster bring-up; movies are unavailable
#
# Native inputs come from the desktop port. By default:
#   NATIV_ROOT       = ../nativ
#   GAME_RECOMP_DIR  = $NATIV_ROOT/dump/decrypted/PCSG00615/recomp
# Override them in the environment if your tree lives elsewhere.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/android_env.sh"

WITH_FFMPEG=1
for arg in "$@"; do
    case "$arg" in
        --no-ffmpeg) WITH_FFMPEG=0 ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done
export WITH_FFMPEG

if [ ! -x "$ANDROID_ADB" ]; then
    echo "Android SDK not found at $ANDROID_SDK (adb missing)" >&2
    exit 1
fi

"$ROOT/scripts/fetch_android_deps.sh"
"$ROOT/scripts/build_sdl3_android.sh"
if [ "$WITH_FFMPEG" = "1" ]; then
    "$ROOT/scripts/build_ffmpeg_android.sh"
else
    echo "FFmpeg: skipped (--no-ffmpeg); movie decoding will be unavailable"
fi

export NATIV_ROOT="${NATIV_ROOT:-$ROOT/../nativ}"

mkdir -p "$ROOT/app/src/main/jniLibs/arm64-v8a"
cp -f "$ROOT/third_party/sdl3-android/lib/libSDL3.so" "$ROOT/app/src/main/jniLibs/arm64-v8a/libSDL3.so"

if [ ! -f "$ROOT/local.properties" ]; then
    printf 'sdk.dir=%s\n' "$ANDROID_SDK" > "$ROOT/local.properties"
fi

cd "$ROOT"
./gradlew :app:assembleDebug

APK="$ROOT/app/build/outputs/apk/debug/app-debug.apk"
if [ -f "$APK" ]; then
    echo
    echo "APK: $APK"
    echo "Install and push data with: scripts/install_android.sh"
else
    echo "Gradle finished without $APK" >&2
    exit 1
fi

#!/usr/bin/env bash
# Build SDL3 3.4.16 for Android arm64-v8a and install it under third_party/sdl3-android.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/android_env.sh"

SRC="$ROOT/third_party/sdl3-src"
PREFIX="$ROOT/third_party/sdl3-android"
BUILD="$ROOT/work/sdl3-android"

if [ ! -f "$SRC/CMakeLists.txt" ]; then
    echo "SDL3 source missing: run scripts/fetch_android_deps.sh" >&2
    exit 1
fi
if [ ! -f "$ANDROID_NDK/build/cmake/android.toolchain.cmake" ]; then
    echo "Android NDK not found at $ANDROID_NDK" >&2
    exit 1
fi

if [ -f "$PREFIX/lib/libSDL3.so" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "SDL3 already built: $PREFIX/lib/libSDL3.so"
    exit 0
fi

"$ANDROID_CMAKE" -S "$SRC" -B "$BUILD" -G Ninja \
    -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a \
    -DANDROID_PLATFORM=android-26 \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DSDL_SHARED=ON \
    -DSDL_STATIC=OFF \
    -DSDL_TESTS=OFF \
    -DSDL_EXAMPLES=OFF \
    -DSDL_INSTALL_TESTS=OFF \
    -DSDL_INSTALL_DOCS=OFF

"$ANDROID_CMAKE" --build "$BUILD" --parallel "${JOBS:-8}"
"$ANDROID_CMAKE" --install "$BUILD"

if [ ! -f "$PREFIX/lib/libSDL3.so" ]; then
    echo "SDL3 build finished without libSDL3.so" >&2
    exit 1
fi
echo "SDL3 ready: $PREFIX/lib/libSDL3.so"

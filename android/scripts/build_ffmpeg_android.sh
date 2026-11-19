#!/usr/bin/env bash
# Build the pinned FFmpeg (H.264 + AAC only) and the raw AAC shim for Android arm64-v8a.
# Optional: without this, the game boots and skips/fails movies instead of decoding them.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/android_env.sh"

SRC="$ROOT/third_party/ffmpeg-src"
PREFIX="$ROOT/third_party/ffmpeg-android"
BUILD="$ROOT/work/ffmpeg-android"
NATIV_ROOT="${NATIV_ROOT:-$ROOT/../nativ}"
API=26

if [ ! -f "$SRC/configure" ]; then
    echo "FFmpeg source missing: run scripts/fetch_android_deps.sh" >&2
    exit 1
fi
if [ ! -f "$ANDROID_NDK/build/cmake/android.toolchain.cmake" ]; then
    echo "Android NDK not found at $ANDROID_NDK" >&2
    exit 1
fi

case "$(uname -s)" in
    Darwin) HOST_TAG=darwin-x86_64 ;;
    Linux)  HOST_TAG=linux-x86_64 ;;
    *) echo "unsupported host: $(uname -s)" >&2; exit 1 ;;
esac
TOOLCHAIN="$ANDROID_NDK/toolchains/llvm/prebuilt/$HOST_TAG"
CC="$TOOLCHAIN/bin/aarch64-linux-android$API-clang"
CXX="$TOOLCHAIN/bin/aarch64-linux-android$API-clang++"
AR="$TOOLCHAIN/bin/llvm-ar"
NM="$TOOLCHAIN/bin/llvm-nm"
RANLIB="$TOOLCHAIN/bin/llvm-ranlib"
STRIP="$TOOLCHAIN/bin/llvm-strip"

if [ -f "$PREFIX/lib/libavcodec.a" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "FFmpeg already built: $PREFIX/lib/libavcodec.a"
    exit 0
fi

mkdir -p "$BUILD" "$PREFIX"
cd "$SRC"
./configure \
    --prefix="$PREFIX" \
    --target-os=android \
    --arch=aarch64 \
    --cpu=armv8-a \
    --enable-cross-compile \
    --sysroot="$TOOLCHAIN/sysroot" \
    --cc="$CC" \
    --cxx="$CXX" \
    --ar="$AR" \
    --nm="$NM" \
    --ranlib="$RANLIB" \
    --strip="$STRIP" \
    --enable-static \
    --disable-shared \
    --enable-pic \
    --disable-everything \
    --disable-programs \
    --disable-doc \
    --disable-network \
    --disable-autodetect \
    --disable-avdevice \
    --disable-avformat \
    --disable-swscale \
    --disable-swresample \
    --disable-avfilter \
    --disable-debug \
    --enable-decoder=h264 \
    --enable-parser=h264 \
    --enable-parser=hevc \
    --enable-decoder=aac \
    --extra-cflags="-fPIC -O2" \
    --extra-ldflags="-fPIC"

make -j"${JOBS:-8}"
make install

# The AAC frame callback shim (runtime/platform/ffmpeg/rawdec.c). It needs FFmpeg's private
# headers, hence -I"$SRC"; the configuration headers are generated in the source tree.
"$CC" -O2 -fPIC -I"$SRC" -c "$NATIV_ROOT/runtime/platform/ffmpeg/rawdec.c" -o "$BUILD/rawdec.o"
"$AR" rcs "$PREFIX/lib/libnativ_rawdec.a" "$BUILD/rawdec.o"

echo "FFmpeg ready: $PREFIX/lib/libavcodec.a, $PREFIX/lib/libnativ_rawdec.a"

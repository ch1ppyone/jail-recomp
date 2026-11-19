#!/usr/bin/env bash
# Fetch the pinned source trees used by the Android build.
# SDL3 is required; FFmpeg is optional (the game boots without it, but movies do not decode).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
THIRD="$ROOT/third_party"
DL="$THIRD/dl"
mkdir -p "$DL"

SDL_VERSION=3.4.10
SDL_SHA=12b34280415ec8418c864408b93d008a20a6530687ee613d60bfbd20411f2785
FFMPEG_VERSION=7.1.1
FFMPEG_SHA=733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

fetch() {
    local url=$1 file="$DL/$2" want=$3
    if [ ! -f "$file" ]; then
        echo "Downloading $(basename "$file")..."
        curl -fL --retry 5 --retry-all-errors -o "$file.part" "$url"
        mv "$file.part" "$file"
    fi
    local got
    got=$(sha256 "$file")
    if [ "$got" != "$want" ]; then
        echo "checksum mismatch: $file (expected $want, got $got)" >&2
        exit 1
    fi
}

if [ ! -f "$THIRD/sdl3-src/CMakeLists.txt" ]; then
    fetch "https://github.com/libsdl-org/SDL/releases/download/release-$SDL_VERSION/SDL3-$SDL_VERSION.tar.gz" \
          "SDL3-$SDL_VERSION.tar.gz" "$SDL_SHA"
    rm -rf "$THIRD/sdl3-src"
    mkdir -p "$THIRD/sdl3-src"
    tar xzf "$DL/SDL3-$SDL_VERSION.tar.gz" -C "$THIRD/sdl3-src" --strip-components=1
    echo "SDL3 source ready: $THIRD/sdl3-src"
else
    echo "SDL3 source already present: $THIRD/sdl3-src"
fi

if [ "${WITH_FFMPEG:-1}" != "0" ] && [ ! -f "$THIRD/ffmpeg-src/configure" ]; then
    fetch "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" \
          "ffmpeg-$FFMPEG_VERSION.tar.xz" "$FFMPEG_SHA"
    rm -rf "$THIRD/ffmpeg-src"
    mkdir -p "$THIRD/ffmpeg-src"
    tar xJf "$DL/ffmpeg-$FFMPEG_VERSION.tar.xz" -C "$THIRD/ffmpeg-src" --strip-components=1
    echo "FFmpeg source ready: $THIRD/ffmpeg-src"
fi

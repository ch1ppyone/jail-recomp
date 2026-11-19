#!/usr/bin/env bash
# Build the signed release APK and stage it with its checksum.
#
#   scripts/release_apk.sh v0.1.1
#
# The signing key lives in data/keystore/ (ignored by Git). Keep it safe: an
# update must be signed with the same key as the installed copy.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/android_env.sh"
TAG="${1:?usage: scripts/release_apk.sh vX.Y.Z}"
PROPS="$ROOT/../data/keystore/keystore.properties"

if [ ! -f "$PROPS" ]; then
    echo "missing $PROPS: the release APK would be unsigned" >&2
    echo "create the keystore first (see README, Android release signing)" >&2
    exit 1
fi

cd "$ROOT"
./gradlew :app:assembleRelease

APK="$ROOT/app/build/outputs/apk/release/app-release.apk"
[ -f "$APK" ] || { echo "no release APK at $APK" >&2; exit 1; }

OUT="$ROOT/../nativ/build/release/$TAG"
mkdir -p "$OUT"
DEST="$OUT/JAIL-$TAG-android-arm64.apk"
cp -f "$APK" "$DEST"

SIGNER=$(find "$ANDROID_SDK/build-tools" -name apksigner -type f 2>/dev/null | sort -V | tail -1)
if [ -n "$SIGNER" ]; then
    "$SIGNER" verify --print-certs "$DEST" | head -4
else
    echo "apksigner not found: cannot verify the signature" >&2
fi

if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$DEST" | tee "$OUT/android-sha.txt"
else
    shasum -a 256 "$DEST" | tee "$OUT/android-sha.txt"
fi
echo "staged: $DEST"

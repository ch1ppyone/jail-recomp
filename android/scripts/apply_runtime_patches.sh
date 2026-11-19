#!/usr/bin/env bash
# Apply the Android portability fixes to a Nativ checkout.
#
# The patches are small and independent of the Android project:
#   ngs.c      no <execinfo.h>/backtrace on bionic (diagnostic-only call chain)
#   gfx_gpu.c  realpath() needs a PATH_MAX buffer under Android's FORTIFY
#   video.c    display.c references video_last_picture_frame even without FFmpeg
#
# The current ../nativ checkout in this workspace already has them. Re-run this
# script after resetting/updating the runtime.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NATIV_ROOT="${NATIV_ROOT:-$ROOT/../nativ}"
PATCH_DIR="$ROOT/patches"

if [ ! -d "$NATIV_ROOT/runtime" ]; then
    echo "Nativ runtime not found: $NATIV_ROOT" >&2
    exit 1
fi

for p in "$PATCH_DIR"/*.patch; do
    [ -e "$p" ] || continue
    if patch -p2 -d "$NATIV_ROOT" --dry-run --forward < "$p" >/dev/null 2>&1; then
        patch -p2 -d "$NATIV_ROOT" --forward < "$p"
        echo "applied: $(basename "$p")"
    else
        echo "skipped (already applied or conflicting): $(basename "$p")"
    fi
done

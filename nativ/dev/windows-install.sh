#!/bin/bash
# A self-contained Windows install of Project Nativ in one folder, made on macOS or Linux: windows-install.sh <folder>
#   <folder>/                   the shipped tools (vitarecomp dist: pipeline, runtime, packs, ...) and version.txt
#   <folder>/toolchain/         llvm-mingw for Windows hosts (the compiler a game build runs on the player's PC), SDL3,
#                               zlib and FFmpeg's H.264 decoder built for Windows (runtime/platform/win/setup-toolchain.sh's,
#                               without its downloads and build trees), each with its licence
#   <folder>/python/            python-build-standalone for Windows, requirements.txt's packages in its site-packages
#   <folder>/Tokyo Ghoul JAIL.exe  the launcher; it finds the folder from where it sits
# Run again over the same folder to update it (dist removes only what it wrote; python and llvm-mingw are kept when
# current). x86-64 Windows 10 and later. Needs the cross toolchain built here first ($ATIV_WIN_TOOLCHAIN, default
# ~/toolchains/ativ-win: runtime/platform/win/setup-toolchain.sh). The player's library is not part of it.
# NATIV_SIGN_CMD: a command that signs one Windows program in place, given its path (signtool, osslsigncode or a signing
# service's client, with your certificate): the launcher is signed with it. Unset: unsigned, as before.
set -euo pipefail
PY_VER=3.13.17
PY_REL=20261021
PY_SHA=e10b46d9b03a3a494297f336770f55f86474d683061137b1cf595e12e47bcef5   # x86_64-pc-windows-msvc-install_only
LM_VER=20261006
LM_SHA=317492c456aa27ee607a5919f1d2d38dcdc1112516a24d0bf4b00d078f52d17a   # llvm-mingw-<ver>-ucrt-x86_64.zip (Windows hosts)
H=$(cd "$(dirname "$0")" && pwd); ROOT=$(dirname "$H")
OUT=${1:?usage: windows-install.sh <folder>}; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
WT=${ATIV_WIN_TOOLCHAIN:-$HOME/toolchains/ativ-win}
[[ -f $WT/SDL3/x86_64-w64-mingw32/bin/SDL3.dll && -f $WT/ffmpeg/lib/libavcodec.a && -f $WT/zlib/lib/libz.a ]] || { echo "no Windows cross toolchain at $WT: run runtime/platform/win/setup-toolchain.sh"; exit 1; }
PYX=${PYTHON:-$ROOT/.venv/bin/python}; [[ -x $PYX ]] || PYX=python3
DL=$WT/dl; mkdir -p "$DL"
verify() { local h; h=$(sha256sum "$1" 2>/dev/null | awk '{print $1}'); [[ -n $h ]] || h=$(shasum -a 256 "$1" | awk '{print $1}'); [[ $h == "$2" ]] && return; echo "checksum mismatch: $1 (expected $2, got $h)"; rm -f "$1"; exit 1; }
fetch() { [[ -f $DL/$1 ]] || { curl -fL --retry 3 -o "$DL/$1.part" "$2" && verify "$DL/$1.part" "$3" && mv -f "$DL/$1.part" "$DL/$1"; }; }

# the tools
NATIV_DIST_BUILT=0 "$PYX" "$ROOT/pipeline/vitarecomp.py" dist "$OUT"   # (not this machine's launcher: Windows' is built below)

# the toolchain: the libraries and headers builds need, each with its licence; the compiler for Windows hosts
mkdir -p "$OUT/toolchain/SDL3"
rsync -a --delete --exclude cmake --exclude pkgconfig "$WT/SDL3/x86_64-w64-mingw32/" "$OUT/toolchain/SDL3/x86_64-w64-mingw32/"
cp "$WT/SDL3/LICENSE.txt" "$OUT/toolchain/SDL3/LICENSE.txt"
for d in zlib ffmpeg; do rsync -a --delete --exclude pkgconfig "$WT/$d/" "$OUT/toolchain/$d/"; done
mkdir -p "$OUT/toolchain/zlib/share/licenses" "$OUT/toolchain/ffmpeg/share/licenses"
cp "$WT/zlib-src/LICENSE" "$OUT/toolchain/zlib/share/licenses/LICENSE"
cp "$WT/ffmpeg-src/LICENSE.md" "$WT/ffmpeg-src/COPYING.LGPLv2.1" "$OUT/toolchain/ffmpeg/share/licenses/"
FV=$(cat "$WT/ffmpeg-src/VERSION" 2>/dev/null || cat "$WT/ffmpeg-src/RELEASE")
printf 'FFmpeg %s (LGPL 2.1 or later), unmodified: https://ffmpeg.org/releases/ffmpeg-%s.tar.xz\nbuilt by runtime/platform/win/setup-toolchain.sh with only the H.264 and AAC decoders (plus libnativ_rawdec.a, runtime/platform/ffmpeg/rawdec.c)\n' "$FV" "$FV" > "$OUT/toolchain/ffmpeg/share/licenses/SOURCE"
if [[ "$(cat "$OUT/toolchain/llvm-mingw/.nativ-version" 2>/dev/null)" != "$LM_VER" ]]; then
  A=llvm-mingw-$LM_VER-ucrt-x86_64.zip
  fetch "$A" "https://github.com/mstorsjo/llvm-mingw/releases/download/$LM_VER/$A" "$LM_SHA"
  rm -rf "$OUT/toolchain/llvm-mingw" "$OUT/toolchain/llvm-mingw.tmp"; mkdir -p "$OUT/toolchain/llvm-mingw.tmp"
  (cd "$OUT/toolchain/llvm-mingw.tmp" && unzip -q "$DL/$A")
  mv "$OUT/toolchain/llvm-mingw.tmp/llvm-mingw-$LM_VER-ucrt-x86_64" "$OUT/toolchain/llvm-mingw"; rmdir "$OUT/toolchain/llvm-mingw.tmp"
  echo "$LM_VER" > "$OUT/toolchain/llvm-mingw/.nativ-version"
fi

# Python for Windows, and requirements.txt's packages as Windows wheels (pip here picks them for that platform)
if [[ "$(cat "$OUT/python/.nativ-version" 2>/dev/null)" != "$PY_VER+$PY_REL" ]]; then
  A=cpython-$PY_VER+$PY_REL-x86_64-pc-windows-msvc-install_only.tar.gz
  fetch "$A" "https://github.com/astral-sh/python-build-standalone/releases/download/$PY_REL/$A" "$PY_SHA"
  rm -rf "$OUT/python"; tar xzf "$DL/$A" -C "$OUT"   # (unpacks as python/)
  echo "$PY_VER+$PY_REL" > "$OUT/python/.nativ-version"
fi
# PyQt6 is split into PyQt6, PyQt6-Qt6 and PyQt6-sip; keep dependency
# resolution enabled so a clean Windows install gets the Qt DLLs and plugins.
# PyQt6 is split into Python bindings, Qt6 DLLs and sip. Install all three;
# the old --no-deps form left a launcher that silently failed on Windows.
"$PYX" -m pip install --quiet --disable-pip-version-check --no-warn-script-location --upgrade --only-binary=:all: \
  --platform win_amd64 --python-version "${PY_VER%.*}" --implementation cp --target "$OUT/python/Lib/site-packages" -r "$ROOT/requirements-launcher.txt"

# the launcher, cross-built with the developer's toolchain, at the top of the folder
mkdir -p "$OUT/launcher"
cp "$ROOT/../src/launcher/pyqt_launcher.py" "$OUT/launcher/pyqt_launcher.py"
 # Use the same JAIL artwork as the macOS app, not the Android launcher art.
ICON="$ROOT/assets/jail/icon-macos-512.png"
if [[ -f "$ICON" ]]; then
  "$PYX" - "$ICON" "$OUT/launcher/jail.ico" <<'PY'
import struct, sys
# Keep the source PNG as a PNG-compressed ICO image. This needs no Pillow and
# is supported by Windows Vista and later (the release target is Windows 10+).
data = open(sys.argv[1], "rb").read()
if data[:8] != b"\x89PNG\r\n\x1a\n": raise SystemExit("icon is not PNG")
w, h = struct.unpack(">II", data[16:24])
size = 0 if w >= 256 else w
header = struct.pack("<HHH", 0, 1, 1)
entry = struct.pack("<BBBBHHII", size, 0 if h >= 256 else h, 0, 0, 1, 32, len(data), 22)
open(sys.argv[2], "wb").write(header + entry + data)
PY
  printf '1 ICON "%s"\n' "$OUT/launcher/jail.ico" > "$OUT/launcher/jail.rc"
  "$WT/llvm-mingw/bin/x86_64-w64-mingw32-windres" "$OUT/launcher/jail.rc" -O coff -o "$OUT/launcher/jail_res.o"
  RES="$OUT/launcher/jail_res.o"
else
  RES=""
fi
"$WT/llvm-mingw/bin/x86_64-w64-mingw32-clang++" -O2 -std=c++17 -municode -mwindows "$ROOT/launcher/pyqt_host.cpp" ${RES:+"$RES"} -o "$OUT/Tokyo Ghoul JAIL.exe"
# The host is linked by llvm-mingw and needs these runtime DLLs next to the
# executable on a clean Windows install (the toolchain directory is not on PATH).
cp "$WT/llvm-mingw/x86_64-w64-mingw32/bin/libc++.dll" "$OUT/libc++.dll"
cp "$WT/llvm-mingw/x86_64-w64-mingw32/bin/libunwind.dll" "$OUT/libunwind.dll"
mkdir -p "$OUT/data"
cat > "$OUT/data/README.txt" <<'EOF'
Put the game's own files here before starting the launcher:
  PCSG00615.pkg
  work.bin
  PSVUPDAT.PUP
EOF
[[ -n ${NATIV_SIGN_CMD:-} ]] && $NATIV_SIGN_CMD "$OUT/Tokyo Ghoul JAIL.exe"
echo "install: $OUT ($(cat "$OUT/version.txt"); $(du -sh "$OUT" | cut -f1))"

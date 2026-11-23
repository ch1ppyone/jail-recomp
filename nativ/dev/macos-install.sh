#!/bin/bash
# The Mac install of Tokyo Ghoul: JAIL: one self-contained app, macos-install.sh <folder> -> <folder>/Tokyo Ghoul JAIL.app
#   Contents/MacOS/Tokyo Ghoul JAIL  a tiny launcher that runs the bundled Python and the PyQt6 UI in Resources.
#                                   The release's data/ (PKG, work.bin, PUP) sits beside the .app; generated files go to
#                                   ~/Library/Application Support/TokyoGhoulJAIL/JAIL.
#   Contents/Resources/             the shipped tools (vitarecomp dist: pipeline, runtime, packs, ...), version.txt,
#                                   toolchain/ (SDL3, SPIRV-Cross and FFmpeg's H.264 decoder: runtime/platform/macos/
#                                   setup-toolchain.sh's, without its downloads and build trees) and python/
#                                   (python-build-standalone with requirements-launcher.txt installed)
# Nothing writes inside the app once it's made (a signed one must match its signature): games, builds and settings live
# in the player's library and settings folders, compiled Python in the settings folder (PYTHONPYCACHEPREFIX).
# Run again over the same folder to update it (dist removes only what it wrote; python is kept when current). Apple
# silicon (arm64), macOS 11 (Big Sur) and later: every M-series Mac. Needs the toolchain built here first ($ATIV_MAC_TOOLCHAIN, default
# ~/toolchains/ativ-mac). Signing, notarising and the .dmg: dev/release.sh.
set -euo pipefail
PY_VER=3.13.17
PY_REL=20261021
PY_SHA=9c985cbf327425873469896ce748c7134b6deca8edb81e93c589ad2fc5aff445   # aarch64-apple-darwin-install_only
H=$(cd "$(dirname "$0")" && pwd); ROOT=$(dirname "$H")
DEST=${1:?usage: macos-install.sh <folder>}; mkdir -p "$DEST"; DEST=$(cd "$DEST" && pwd)
APP="$DEST/Tokyo Ghoul JAIL.app"; OUT="$APP/Contents/Resources"; mkdir -p "$OUT" "$APP/Contents/MacOS"
mkdir -p "$DEST/data"
cat > "$DEST/data/README.txt" <<'EOF'
Put the game's own files here before starting the launcher:
  PCSG00615.pkg
  work.bin
  PSVUPDAT.PUP
EOF
MT=${ATIV_MAC_TOOLCHAIN:-$HOME/toolchains/ativ-mac}
[[ -f $MT/SDL3/lib/libSDL3.0.dylib && -f $MT/spirv-cross/lib/libspirv-cross-c.a ]] || { echo "no Mac toolchain at $MT: run runtime/platform/macos/setup-toolchain.sh"; exit 1; }
PYX=${PYTHON:-$ROOT/.venv/bin/python}; [[ -x $PYX ]] || PYX=python3

# the tools
NATIV_DIST_BUILT=0 "$PYX" "$ROOT/pipeline/vitarecomp.py" dist "$OUT"   # (the launcher is built below, as the app's own program)

# the toolchain: the libraries and headers builds need, not the downloads, sources or build trees
mkdir -p "$OUT/toolchain"
for d in SDL3 spirv-cross ffmpeg; do rsync -a --delete --exclude cmake --exclude pkgconfig --exclude 'libSDL3_test.a' "$MT/$d/" "$OUT/toolchain/$d/"; done

# Python
if [[ ! -x $OUT/python/bin/python3 || "$("$OUT/python/bin/python3" -c 'import platform; print(platform.python_version())')" != "$PY_VER" ]]; then
  DL=$MT/dl; A=cpython-$PY_VER+$PY_REL-aarch64-apple-darwin-install_only.tar.gz
  verify() { local h; h=$(sha256sum "$1" 2>/dev/null | awk '{print $1}'); [[ -n $h ]] || h=$(shasum -a 256 "$1" | awk '{print $1}'); [[ $h == "$2" ]] && return; echo "checksum mismatch: $1 (expected $2, got $h)"; rm -f "$1"; exit 1; }
  [[ -f $DL/$A ]] || { curl -fL --retry 3 -o "$DL/$A.part" "https://github.com/astral-sh/python-build-standalone/releases/download/$PY_REL/$A" && verify "$DL/$A.part" "$PY_SHA" && mv -f "$DL/$A.part" "$DL/$A"; }
  rm -rf "$OUT/python"; tar xzf "$DL/$A" -C "$OUT"   # (unpacks as python/)
fi
"$OUT/python/bin/python3" -m pip install --quiet --disable-pip-version-check --no-warn-script-location -r "$ROOT/requirements-launcher.txt"

# The launcher is the project's PyQt6 UI, run by the bundled Python. The app's
# own executable is a small script; LaunchServices starts it and the UI takes over.
mkdir -p "$OUT/launcher"
cp "$ROOT/../src/launcher/pyqt_launcher.py" "$OUT/launcher/pyqt_launcher.py"
cat > "$APP/Contents/MacOS/Tokyo Ghoul JAIL" <<'LAUNCH'
#!/bin/sh
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
export JAIL_APP_RESOURCES="$RES"
APP_DIR="$(cd "$RES/../.." && pwd)"
RELEASE_DATA="$(cd "$APP_DIR/.." && pwd)/data"
if [ -d "$RELEASE_DATA" ]; then export JAIL_DATA="$RELEASE_DATA"; fi
export ATIV_MAC_TOOLCHAIN="$RES/toolchain"
export PYTHONPYCACHEPREFIX="$HOME/Library/Application Support/TokyoGhoulJAIL/JAIL/pycache"
exec "$RES/python/bin/python3" "$RES/launcher/pyqt_launcher.py" "$@"
LAUNCH
chmod +x "$APP/Contents/MacOS/Tokyo Ghoul JAIL"

# The icon comes from the game's Android launcher artwork (the JAIL eye).
# nativ.icns is only a fallback for a checkout without the Android project.
ICON_DIR=$(mktemp -d)/jail.iconset
mkdir -p "$ICON_DIR"
SRC_ICON="$ROOT/../android/app/src/main/res/drawable-nodpi/launcher_legacy.png"
if [ -f "$SRC_ICON" ]; then
  sips -z 16 16 "$SRC_ICON" --out "$ICON_DIR/icon_16x16.png" >/dev/null
  sips -z 32 32 "$SRC_ICON" --out "$ICON_DIR/icon_16x16@2x.png" >/dev/null
  sips -z 32 32 "$SRC_ICON" --out "$ICON_DIR/icon_32x32.png" >/dev/null
  sips -z 64 64 "$SRC_ICON" --out "$ICON_DIR/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "$SRC_ICON" --out "$ICON_DIR/icon_128x128.png" >/dev/null
  sips -z 256 256 "$SRC_ICON" --out "$ICON_DIR/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "$SRC_ICON" --out "$ICON_DIR/icon_256x256.png" >/dev/null
  sips -z 512 512 "$SRC_ICON" --out "$ICON_DIR/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "$SRC_ICON" --out "$ICON_DIR/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "$SRC_ICON" --out "$ICON_DIR/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$ICON_DIR" -o "$OUT/jail.icns"
else
  cp "$ROOT/assets/brand/nativ.icns" "$OUT/jail.icns"
fi
V=$(cat "$OUT/version.txt"); BV=${V#v}; [[ $BV =~ ^[0-9]+(\.[0-9]+){1,2}$ ]] || BV=0.0.0   # (the bundle's version: a release's number)
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Tokyo Ghoul JAIL</string>
  <key>CFBundleDisplayName</key><string>Tokyo Ghoul: JAIL</string>
  <key>CFBundleIdentifier</key><string>dev.ch1ppy.jail.launcher</string>
  <key>CFBundleExecutable</key><string>Tokyo Ghoul JAIL</string>
  <key>CFBundleIconFile</key><string>jail</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$BV</string>
  <key>CFBundleVersion</key><string>$BV</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.games</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSCameraUsageDescription</key><string>Some games use the Vita's rear camera; Nativ can use this Mac's camera for it.</string>
  <key>NSLocalNetworkUsageDescription</key><string>Online play finds other players on your network.</string>
</dict></plist>
EOF
echo "install: $APP ($V; $(du -sh "$APP" | cut -f1))"

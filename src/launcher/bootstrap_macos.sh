#!/bin/zsh
# SPDX-License-Identifier: GPL-3.0-or-later
# Prepare the local Python and native build prerequisites before opening PyQt.
set -euo pipefail
ROOT=${0:A:h:h:h}
NATIV=$ROOT/nativ
VENV=$NATIV/.venv
PY=$VENV/bin/python
TOOLCHAIN=${ATIV_MAC_TOOLCHAIN:-$HOME/toolchains/ativ-mac}

say() { print "[JAIL setup] $*"; }
fail() { print -u2 "[JAIL setup] ERROR: $*"; exit 1; }

command -v python3 >/dev/null || fail "Python 3 is required. Install it from python.org or Homebrew."
if ! xcode-select -p >/dev/null 2>&1; then
  fail "Apple Command Line Tools are required. Run: xcode-select --install"
fi

if [[ ! -x $PY ]]; then
  say "Creating Python virtual environment: $VENV"
  python3 -m venv "$VENV" || fail "Could not create the Python virtual environment."
fi

if "$PY" -c 'import Crypto, capstone, PyQt6' >/dev/null 2>&1; then
  say "Python dependencies already installed"
else
  say "Installing Python dependencies (including pycryptodome and PyQt6)"
  "$PY" -m pip install --upgrade pip setuptools wheel
  "$PY" -m pip install -r "$NATIV/requirements-launcher.txt"
fi

if command -v brew >/dev/null 2>&1; then
  missing=()
  command -v cmake >/dev/null 2>&1 || missing+=(cmake)
  command -v ninja >/dev/null 2>&1 || missing+=(ninja)
  if (( ${#missing[@]} )); then
    say "Installing native build tools with Homebrew: ${missing[*]}"
    brew install $missing
  fi
else
  say "Homebrew not found; cmake/ninja must already be installed."
fi

command -v cmake >/dev/null 2>&1 || fail "cmake is required. Install Homebrew, then run: brew install cmake ninja"
if [[ ! -f $TOOLCHAIN/SDL3/lib/libSDL3.0.dylib || ! -f $TOOLCHAIN/spirv-cross/lib/libspirv-cross-c.a || ! -f $TOOLCHAIN/ffmpeg/lib/libavcodec.a ]]; then
  say "Building the pinned macOS native toolchain in $TOOLCHAIN"
  ATIV_MAC_TOOLCHAIN="$TOOLCHAIN" zsh "$NATIV/runtime/platform/macos/setup-toolchain.sh"
else
  say "Native toolchain already ready: $TOOLCHAIN"
fi

"$PY" -c 'from Crypto.Cipher import AES; from PyQt6.QtWidgets import QApplication; print("[JAIL setup] Python dependencies OK")'
say "Setup complete."

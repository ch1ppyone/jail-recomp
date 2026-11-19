#!/bin/zsh
# SPDX-License-Identifier: GPL-3.0-or-later
set -e
ROOT=${0:A:h}
zsh "$ROOT/src/launcher/bootstrap_macos.sh"
PY=$ROOT/nativ/.venv/bin/python
exec "$PY" "$ROOT/src/launcher/pyqt_launcher.py"

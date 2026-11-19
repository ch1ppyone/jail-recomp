#!/usr/bin/env bash
# Run the host-side PKG decryptor checks. Needs Python with PyCryptodome and a
# JDK 17 on PATH (or JAVA_HOME).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PYTHON:-python3}"
exec "$PY" "$ROOT/android/tests/decryptor_test.py" "$@"

#!/usr/bin/env bash
set -eu
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${INFINI_PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then PYTHON_BIN="$(command -v python || command -v python3)"; fi
exec "$PYTHON_BIN" "$ROOT/tools/validate_release.py" "$@"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-}"

python_ok() {
  "$@" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

if [[ -n "$PYTHON_BIN" ]]; then
  if ! python_ok "$PYTHON_BIN"; then
    echo "error: PYTHON is set to '$PYTHON_BIN', but it is not a working Python 3.10+ executable." >&2
    exit 1
  fi
else
  PYTHON_BIN=""
  for candidate in python python3 "py -3"; do
    read -r -a candidate_cmd <<< "$candidate"
    if command -v "${candidate_cmd[0]}" >/dev/null 2>&1 && python_ok "${candidate_cmd[@]}"; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "error: no working Python 3.10+ executable was found. Install Python first." >&2
  exit 1
fi

read -r -a PYTHON_CMD <<< "$PYTHON_BIN"
echo "Using Python: $("${PYTHON_CMD[@]}" --version)"

if ! "${PYTHON_CMD[@]}" -m pip --version >/dev/null 2>&1; then
  VENV_DIR="$SCRIPT_DIR/.venv"
  echo "Python pip is unavailable; creating virtual environment at $VENV_DIR"
  "${PYTHON_CMD[@]}" -m venv "$VENV_DIR"
  PYTHON_CMD=("$VENV_DIR/bin/python")
  echo "Using virtualenv Python: $("${PYTHON_CMD[@]}" --version)"
fi

"${PYTHON_CMD[@]}" -m pip install -r "$SCRIPT_DIR/requirements.txt"
"${PYTHON_CMD[@]}" -m playwright install chromium

echo "Setup complete."

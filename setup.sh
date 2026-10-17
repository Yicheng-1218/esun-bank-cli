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

if [[ "$PYTHON_BIN" == "py -3" ]]; then
  PYTHON_CMD=(py -3)
else
  PYTHON_CMD=("$PYTHON_BIN")
fi
echo "Using Python: $("${PYTHON_CMD[@]}" --version)"

VENV_DIR="$SCRIPT_DIR/.venv"
if [[ ! -e "$VENV_DIR" && ! -L "$VENV_DIR" ]]; then
  echo "Creating virtual environment at $VENV_DIR"
  if command -v uv >/dev/null 2>&1; then
    uv venv --python "$PYTHON_BIN" "$VENV_DIR"
  else
    "${PYTHON_CMD[@]}" -m venv "$VENV_DIR"
  fi
fi
PYTHON_CMD=("$VENV_DIR/bin/python")
if [[ -L "$VENV_DIR" || ! -f "$VENV_DIR/pyvenv.cfg" || ! -x "${PYTHON_CMD[0]}" ]] || ! "${PYTHON_CMD[@]}" -c 'import sys; from pathlib import Path; raise SystemExit(not (sys.version_info >= (3, 10) and sys.prefix != sys.base_prefix and Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()))' "$VENV_DIR" >/dev/null 2>&1; then
  echo "error: invalid skill virtualenv at $VENV_DIR." >&2
  echo "Move aside only '$VENV_DIR', then rerun setup to create a fresh runtime." >&2
  printf 'run: bash %q\n' "$SCRIPT_DIR/setup.sh" >&2
  exit 1
fi
echo "Using virtualenv Python: $("${PYTHON_CMD[@]}" --version)"

if command -v uv >/dev/null 2>&1; then
  uv pip install --python "${PYTHON_CMD[0]}" -r "$SCRIPT_DIR/requirements.txt"
else
  "${PYTHON_CMD[@]}" -m pip install -r "$SCRIPT_DIR/requirements.txt"
fi
if ! "${PYTHON_CMD[@]}" -c 'from playwright.async_api import async_playwright' >/dev/null 2>&1; then
  echo "error: skill virtualenv Playwright import failed. Repair it with setup.sh." >&2
  exit 1
fi
"${PYTHON_CMD[@]}" -m playwright install chromium

echo "Setup complete."

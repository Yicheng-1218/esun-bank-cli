#!/usr/bin/env bash
set -euo pipefail

SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SOURCE" ]]; do
  SOURCE_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" = /* ]] || SOURCE="$SOURCE_DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="$SKILL_DIR/.venv/bin/python"
CLI="$SKILL_DIR/scripts/esun_bank_cli.py"

VENV_DIR="$SKILL_DIR/.venv"
if [[ ! -f "$VENV_DIR/pyvenv.cfg" || ! -x "$PYTHON_BIN" ]] || ! "$PYTHON_BIN" -c 'import sys; from pathlib import Path; raise SystemExit(not (sys.version_info >= (3, 10) and sys.prefix != sys.base_prefix and Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()))' "$VENV_DIR" >/dev/null 2>&1; then
  echo "error: skill virtualenv is missing or invalid: $VENV_DIR" >&2
  echo "If it exists, move aside only '$VENV_DIR', then run setup to create a fresh runtime." >&2
  printf 'run: bash %q\n' "$SKILL_DIR/setup.sh" >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'from playwright.async_api import async_playwright' >/dev/null 2>&1; then
  echo "error: skill virtualenv Playwright is missing or unusable." >&2
  printf 'run: bash %q\n' "$SKILL_DIR/setup.sh" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$CLI" "$@"

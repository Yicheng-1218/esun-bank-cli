"""Offline smoke check for imports and parser construction."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import esun_bank_cli


def main() -> int:
    parser = esun_bank_cli.build_parser()
    args = parser.parse_args(["batch", "twd", "credit"])
    assert esun_bank_cli.resolve_sources(args) == ["twd", "credit"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

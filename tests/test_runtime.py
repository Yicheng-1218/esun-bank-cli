import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import esun_bank_cli


class CliRuntimeTest(unittest.TestCase):
    def test_all_resolves_to_single_batch_order(self):
        parser = esun_bank_cli.build_parser()
        args = parser.parse_args(["all"])
        self.assertEqual(esun_bank_cli.resolve_sources(args), ["twd", "credit", "debit"])

    def test_batch_deduplicates_and_uses_safe_order(self):
        parser = esun_bank_cli.build_parser()
        args = parser.parse_args(["batch", "debit", "twd", "credit", "debit"])
        self.assertEqual(esun_bank_cli.resolve_sources(args), ["twd", "credit", "debit"])

    def test_single_commands_keep_unified_pipeline(self):
        parser = esun_bank_cli.build_parser()
        for name in ("credit", "debit", "twd"):
            args = parser.parse_args([name])
            self.assertEqual(esun_bank_cli.resolve_sources(args), [name])


if __name__ == "__main__":
    unittest.main()

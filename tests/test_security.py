import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import esun_bank_cli
from esun_bank.session import GLOBAL_CREDENTIALS_FILE


class SecurityContractTest(unittest.TestCase):
    def test_default_credential_is_global_not_profile_specific(self):
        self.assertTrue(str(GLOBAL_CREDENTIALS_FILE).endswith("/.hermes/esun-bank/credentials.json"))
        self.assertNotIn("/profiles/", str(GLOBAL_CREDENTIALS_FILE))

    def test_force_login_is_opt_in(self):
        parser = esun_bank_cli.build_parser()
        args = parser.parse_args(["all"])
        self.assertFalse(args.force_login)
        forced = parser.parse_args(["all", "--force-login"])
        self.assertTrue(forced.force_login)

    def test_no_mutation_commands(self):
        parser = esun_bank_cli.build_parser()
        help_text = parser.format_help().lower()
        for forbidden in ("transfer", "pay", "beneficiary", "card-management"):
            self.assertNotIn(forbidden, help_text)


if __name__ == "__main__":
    unittest.main()

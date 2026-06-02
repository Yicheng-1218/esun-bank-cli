import argparse
import contextlib
import io
import os
import stat
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from esun_bank.output import mask_account, mask_sensitive_accounts
from esun_bank.session import CliError, load_credentials, validate_login_url
from esun_bank_cli import build_parser


class SecurityDefaultsTest(unittest.TestCase):
    def test_parser_rejects_url_and_password_options(self):
        parser = build_parser()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit):
                parser.parse_args(["balance", "--url", "https://evil.example"])
            with self.assertRaises(SystemExit):
                parser.parse_args(["balance", "--password", "secret"])

    def test_show_full_accounts_defaults_to_false(self):
        parser = build_parser()
        args = parser.parse_args(["balance"])
        self.assertFalse(args.show_full_accounts)

    def test_validate_login_url_allows_only_esun_https(self):
        self.assertEqual(
            validate_login_url("https://ebank.esunbank.com.tw/index.jsp"),
            "https://ebank.esunbank.com.tw/index.jsp",
        )
        for url in [
            "http://ebank.esunbank.com.tw/index.jsp",
            "https://evil.example/index.jsp",
            "https://ebank.esunbank.com.tw.evil.example/index.jsp",
        ]:
            with self.assertRaises(CliError):
                validate_login_url(url)

    def test_mask_account_preserves_format_and_last_four_digits(self):
        self.assertEqual(mask_account("1234-5678-9012"), "****-****-9012")
        self.assertEqual(mask_account("XXXX-XXXX-1234"), "XXXX-XXXX-1234")
        self.assertEqual(mask_account("1234"), "1234")

    def test_mask_sensitive_accounts_recurses_over_card_and_account_keys(self):
        value = {
            "account": "1234-5678-9012",
            "items": [{"卡號": "1111 2222 3333 4444", "amount": "100"}],
        }
        self.assertEqual(
            mask_sensitive_accounts(value),
            {
                "account": "****-****-9012",
                "items": [{"卡號": "**** **** **** 4444", "amount": "100"}],
            },
        )

    @unittest.skipIf(os.name == "nt", "POSIX file mode check only")
    def test_credentials_file_rejects_group_or_world_readable_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            credentials = Path(temp_dir) / "credentials.json"
            credentials.write_text(
                '{"id":"A123456789","user":"user","password":"secret"}',
                encoding="utf-8",
            )
            credentials.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
            args = argparse.Namespace(
                credentials_file=str(credentials),
                id=None,
                user=None,
                prompt_missing=False,
            )
            with self.assertRaises(CliError):
                load_credentials(args)


if __name__ == "__main__":
    unittest.main()

import argparse
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from unittest.mock import patch

from esun_bank import session


class CredentialTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.global_file = self.root / ".hermes" / "esun-bank" / "credentials.json"
        self.args = argparse.Namespace(
            credentials_file=None,
            prompt_missing=False,
        )

    def write_cred(self, path: Path, label: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "id": f"ID-{label}",
            "user": f"USER-{label}",
            "password": f"PASS-{label}",
        }
        path.write_text(json.dumps(value), encoding="utf-8")
        path.chmod(0o600)
        return value

    def test_global_credential_is_profile_independent(self):
        expected = self.write_cred(self.global_file, "global")
        profile = self.root / ".hermes" / "profiles" / "shaba"
        profile_cred = profile / "esun-bank" / "credentials.json"
        self.write_cred(profile_cred, "profile")

        with patch.object(session, "GLOBAL_CREDENTIALS_FILE", self.global_file), patch.dict(
            os.environ,
            {"HERMES_HOME": str(profile), "HOME": str(self.root)},
            clear=True,
        ):
            self.assertEqual(session.load_credentials(self.args), expected)

    def test_explicit_file_overrides_global(self):
        self.write_cred(self.global_file, "global")
        explicit = self.root / "explicit.json"
        expected = self.write_cred(explicit, "explicit")
        self.args.credentials_file = str(explicit)

        with patch.object(session, "GLOBAL_CREDENTIALS_FILE", self.global_file), patch.dict(
            os.environ, {}, clear=True
        ):
            self.assertEqual(session.load_credentials(self.args), expected)

    def test_env_file_overrides_global(self):
        self.write_cred(self.global_file, "global")
        env_file = self.root / "env.json"
        expected = self.write_cred(env_file, "env")

        with patch.object(session, "GLOBAL_CREDENTIALS_FILE", self.global_file), patch.dict(
            os.environ,
            {"ESUN_CREDENTIALS_FILE": str(env_file)},
            clear=True,
        ):
            self.assertEqual(session.load_credentials(self.args), expected)

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_rejects_open_permissions(self):
        self.write_cred(self.global_file, "global")
        self.global_file.chmod(0o644)

        with patch.object(session, "GLOBAL_CREDENTIALS_FILE", self.global_file), patch.dict(
            os.environ, {}, clear=True
        ):
            with self.assertRaisesRegex(session.CliError, "permissions"):
                session.load_credentials(self.args)


if __name__ == "__main__":
    unittest.main()

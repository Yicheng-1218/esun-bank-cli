import unittest
from datetime import datetime, timezone

from experiments.http_bootstrap_probe import make_envelope


class BootstrapEnvelopeTest(unittest.TestCase):
    def test_taipei_timestamp_and_empty_anonymous_flow(self):
        import json

        now = datetime(2026, 10, 18, 2, 0, tzinfo=timezone.utc)
        envelope = json.loads(make_envelope(now))
        self.assertEqual(envelope["header"], {
            "txnTime": "2026-10-18 10:00:00",
            "txnFlowToken": "",
        })
        self.assertEqual(envelope["requestBody"], {})


if __name__ == "__main__":
    unittest.main()

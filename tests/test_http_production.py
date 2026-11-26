"""Offline tests for the promoted HTTP CLI, statements and private cache."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import esun_bank_cli as cli
from esun_bank.http_card import CardHttp, CardProtocolError
from esun_bank.http_protocol import EsunHttp, HttpProtocolError
from esun_bank.statements import collect_statements, derive_installments, previous_period


class FakeCard:
    def __init__(self):
        self.requests = []
        self.cleaned = False

    def bootstrap_from_handoff(self, **kwargs):
        self.requests.append(("bootstrap", None))

    def fetch(self, source, *, cursor=1):
        self.requests.append(("fetch", source, cursor))
        groups = ([{
            "year": "2026", "month": "11",
            "transDetailList": [{
                "cardNo": "1234567890123456", "merchantName": "Synthetic",
                "paymentAmount": 100, "paymentCurrency": "TWD",
                "transMonthDay": "1102",
            }],
        }] if cursor == 1 else [])
        return {"body": {
            "cardInfoList": [{"cardNo": "1234567890123456", "coBrandedName": "Synthetic"}],
            "transList": groups, "cursor": cursor,
        }}

    def fetch_bill(self, kind, *, period=None):
        self.requests.append(("bill", kind, period))
        if kind == "latest":
            return {"lastBillYearMonth": "202610"}
        if kind == "summary":
            return {
                "billInfo": {
                    "billDate": "20261107", "paymentDueDate": "20261123",
                    "billTotalInfoList": [{"billTotalAmount": 18000, "billTotalCurrency": "TWD"}],
                },
                "feeRewardInfoList": [{"title": "分期利息", "amount": 88, "currency": "TWD"}],
            }
        if period == "202610":
            return {"transList": [{"year": "2026", "month": "09", "transDetailList": [
                {"merchantName": "易遊網 分03期之第02期", "paymentAmount": 8829,
                 "paymentCurrency": "TWD", "transMonthDay": "0901"},
                {"merchantName": "（未到期分期金額8829元 應付總費用年百分率5.98%）",
                 "paymentAmount": None, "paymentCurrency": "TWD"},
            ]}]}
        return {"transList": [{"year": "2026", "month": "09", "transDetailList": [
            {"merchantName": "易遊網 分03期之第01期",
             "paymentAmount": 8830, "paymentCurrency": "TWD"},
        ]}]}

    def clear(self):
        self.cleaned = True


class FakeBank:
    def __init__(self):
        self.events = []
        self.login_accepted = False

    def initialize(self):
        self.events.append("initialize")

    def submit_nonforced_login(self, **kwargs):
        self.events.append("login")
        self.login_accepted = True

    def confirm_session(self):
        self.events.append("confirm")

    def query_twd(self):
        self.events.append("twd")
        return {"resultBody": {
            "twAccountList": [], "queryDeptTxDtlResult": {"detailListData": []}
        }}

    def card_sso_handoff(self, *, purpose="transactions"):
        self.events.append("sso:" + purpose)
        project = "CARDTRANS" if purpose == "transactions" else "CARDBILL"
        return type("Handoff", (), {
            "redirect_url": "https://iesc.esunbank.com/IESC/authMib/mibOAuth?prjcd=" + project + "&tab=credit",
            "token": "synthetic-token",
        })()

    def finish_card_sso_return(self, **kwargs):
        return "https://iesc.esunbank.com/IESC/authMib/mibVerify"

    def logout(self):
        self.events.append("logout")


class FakeHttp:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.cookies = self
        self.cleared = False

    def clear(self):
        self.cleared = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class StatementsTest(unittest.TestCase):
    def test_validate_period(self):
        self.assertEqual(previous_period("202601", 1), "202512")
        with self.assertRaises(ValueError):
            previous_period("202613", 0)

    def test_amount_and_unbilled_balance(self):
        card = FakeCard()
        result = collect_statements(card, months=2)
        self.assertEqual(result["latest_period"], "202610")
        self.assertEqual(len(result["statements"]), 2)
        installments = derive_installments(result)
        self.assertEqual(len(installments["active"]), 1)
        active = installments["active"][0]
        self.assertEqual(active["installment_count"], 3)
        self.assertEqual(active["installment_number"], 2)
        self.assertEqual(active["billed_amount"]["value"], "8829")
        self.assertEqual(active["unbilled_balance"]["value"], "8829")
        self.assertEqual(installments["history"][-1]["status"], "historical_unverified")


class BillHttpContractTest(unittest.TestCase):
    def test_bill_sso_uses_bank_published_system_and_task_id(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as client:
            bank = EsunHttp(client, origin="https://ebank.esunbank.com.tw")
            bank.session_confirmed = True
            with patch.object(bank, "_post", return_value={"resultBody": {
                "redirectUrl": "https://iesc.esunbank.com/IESC/authMib/mibOAuth?prjcd=CARDBILL&tab=credit",
                "token": "synthetic-token",
            }}) as post:
                result = bank.card_sso_handoff(purpose="statements")
            post.assert_called_once_with(bank.SSO, {
                "clientSystemId": "IESC-CARDBILL", "taskId": "CCM01007",
            })
            self.assertIn("CARDBILL", result.redirect_url)
            with self.assertRaises(HttpProtocolError):
                bank.card_sso_handoff(purpose="transfer")

    def test_bill_api_is_restricted_read_only_post_and_uses_bill_bearer(self):
        requests = []

        def transport(request):
            requests.append(request)
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.host, "iesc.esunbank.com")
            self.assertIn("/GW/creditBill/getDetailResult", str(request.url))
            self.assertEqual(json.loads(request.content), {"billPeriod": "202610"})
            self.assertEqual(request.headers["authorization"], "Bearer fake-bearer")
            return httpx.Response(200, json={
                "status": "200", "body": {"rtnCode": "S", "transList": []}
            })

        with httpx.Client(transport=httpx.MockTransport(transport)) as client:
            card = CardHttp(client)
            card.sso_initialized = True
            card._project = "CARDBILL"
            card._bearer = "fake-bearer"
            self.assertEqual(card.fetch_bill("detail", period="202610")["transList"], [])
            self.assertEqual(len(requests), 1)
            with self.assertRaises(CardProtocolError):
                card.fetch_bill("detail", period="20261314")
            with self.assertRaises(CardProtocolError):
                card.fetch_bill("unauthorized", period="202610")


class ProductionCliTest(unittest.TestCase):
    def make_args(self, *rest):
        return cli.build_parser().parse_args(["full", *rest])

    def test_parser_is_read_only_and_http_only(self):
        parser = cli.build_parser()
        self.assertFalse(self.make_args().confirm_live)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["all", "--force-login"])
        self.assertEqual(cli.resolve_sources(self.make_args()), ["twd", "credit", "debit"])
        self.assertEqual(cli.select_extras("full"), ["statements", "installments"])
        self.assertEqual(cli.select_extras("batch", ["credit", "installments"]), ["installments"])

    def test_batch_uses_one_sso_and_one_bill_fetch_group(self):
        bank, card, bill_card = FakeBank(), FakeCard(), FakeCard()
        result = cli.collect_sources(
            bank, card, ["twd", "credit", "debit"],
            bill_card=bill_card, extras=["statements", "installments"], statement_months=2,
        )
        self.assertEqual(result["summary"]["transaction_count"], 2)
        self.assertEqual(bank.events.count("sso:transactions"), 1)
        self.assertEqual(bank.events.count("sso:statements"), 1)
        self.assertEqual([x for x in bill_card.requests if x[0] == "bill" and x[1] == "latest"],
                         [("bill", "latest", None)])
        self.assertEqual(result["installments"]["active"][0]["unbilled_balance"]["value"], "8829")

    def test_pagination_stops_on_empty(self):
        card = FakeCard()
        raw = cli.collect_card_pages(card, "credit", max_pages=4)
        self.assertEqual(len(raw["body"]["transList"]), 1)
        self.assertEqual([e[-1] for e in card.requests if e[0] == "fetch"], [1, 2])

    def test_cache_is_private_and_does_not_contain_credentials(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(cli, "CACHE_DIR", Path(folder) / "cache"):
            cli.write_cache("a" * 64, {"safe": "masked-data"})
            p = cli.CACHE_DIR / ("a" * 64 + ".json")
            self.assertEqual(stat.S_IMODE(cli.CACHE_DIR.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
            self.assertEqual(cli.read_cache("a" * 64, 60), {"safe": "masked-data"})
            self.assertIsNone(cli.read_cache("a" * 64, 0))
            self.assertNotIn("password", p.read_text(encoding="utf-8"))

    def test_cached_only_without_cache_never_logs_in(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(cli, "CACHE_DIR", Path(folder) / "cache"):
            with patch.object(cli, "load_credentials", return_value={"id": "fake", "user": "fake", "password": "fake"}):
                with patch.object(cli.httpx, "Client", side_effect=AssertionError("MUST NOT LOGIN")):
                    with self.assertRaises(cli.CliError):
                        asyncio.run(cli.execute(self.make_args("--cached-only")))

    def test_live_one_login_and_logout(self):
        bank, card, bill_card = FakeBank(), FakeCard(), FakeCard()
        with tempfile.TemporaryDirectory() as folder:
          with (patch.object(cli, "CACHE_DIR", Path(folder) / "cache"),
                patch.object(cli, "load_credentials", return_value={"id": "fake", "user": "fake", "password": "fake"}),
                patch.object(cli, "EsunHttp", return_value=bank),
                patch.object(cli, "CardHttp", side_effect=[card, bill_card]),
                patch.object(cli.httpx, "Client", side_effect=lambda **kwargs: FakeHttp(**kwargs))):
            result = asyncio.run(cli.execute(self.make_args("--confirm-live")))
            self.assertEqual(result["schema_version"], "3.0")
            self.assertEqual(bank.events.count("login"), 1)
            self.assertEqual(bank.events.count("logout"), 1)
            self.assertTrue(card.cleaned)
            self.assertTrue(bill_card.cleaned)
            with patch.object(cli, "load_credentials", return_value={"id": "fake", "user": "fake", "password": "fake"}):
              with patch.object(cli.httpx, "Client", side_effect=AssertionError("CACHE SHOULD HIT")):
                cached = asyncio.run(cli.execute(self.make_args("--cached-only")))
            self.assertEqual(cached["installments"], result["installments"])

    def test_http_stack_has_no_playwright_imports(self):
        for filename in ("scripts/esun_bank_cli.py", "scripts/esun_bank/http_card.py",
                         "scripts/esun_bank/http_protocol.py", "scripts/esun_bank/http_crypto.py"):
            text = (Path(__file__).resolve().parents[1] / filename).read_text(encoding="utf-8")
            self.assertNotIn("import playwright", text)
            self.assertNotIn("async_playwright", text)


if __name__ == "__main__":
    unittest.main()

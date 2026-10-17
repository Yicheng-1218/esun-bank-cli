import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from esun_bank.schema import normalize, one_month_range


class UnifiedSchemaTest(unittest.TestCase):
    def test_all_sources_share_transaction_shape(self):
        _, end = one_month_range()

        credit = {
            "body": {
                "cardInfoList": [{
                    "cardNo": "1234567890123456",
                    "coBrandedName": "Credit",
                    "isPrimaryCard": True,
                }],
                "transList": [{
                    "year": str(end.year),
                    "month": str(end.month),
                    "transDetailList": [{
                        "transMonthDay": end.strftime("%m/%d"),
                        "cardNo": "1234567890123456",
                        "merchantName": "Store",
                        "paymentAmount": "1,234.50",
                        "paymentCurrency": "TWD",
                        "transAmount": "40.00",
                        "transCurrency": "USD",
                        "statusName": "posted",
                    }],
                }],
            }
        }

        debit = {
            "body": {
                "cardInfoList": [{
                    "cardNo": "9999888877776666",
                    "coBrandedName": "Debit",
                    "isPrimaryCard": True,
                }],
                "transList": [{
                    "year": str(end.year),
                    "month": str(end.month),
                    "transDetailList": [{
                        "transMonthDay": end.strftime("%m/%d"),
                        "cardNo": "9999888877776666",
                        "merchantName": "Cafe",
                        "paymentAmount": "100",
                        "paymentCurrency": "TWD",
                        "transAmount": "100",
                        "transCurrency": "TWD",
                        "statusName": "done",
                    }],
                }],
            }
        }

        twd = {
            "resultBody": {
                "twAccountList": [{
                    "accountNo": "0123456789012",
                    "accountAlias": "main",
                }],
                "demandDeptAcc": "0123456789012",
                "queryDeptTxDtlResult": {
                    "detailListData": [{
                        "detailInfo": [{
                            "txDate": end.isoformat(),
                            "demandDeptAcc": "0123456789012",
                            "debitCredit": "支出",
                            "amount": "500",
                            "currency": "TWD",
                            "balance": "10000",
                            "detailTitle": "Transfer",
                            "oppositeBankCode": "808",
                            "oppositeAccount": "9876543210123",
                            "transferMessage": "memo",
                        }]
                    }]
                },
            }
        }

        result = normalize(
            requested=["twd", "credit", "debit"],
            card_payloads={"credit": credit, "debit": debit},
            twd_payload=twd,
        )

        self.assertEqual(result["schema_version"], "3.0")
        self.assertEqual(result["summary"]["transaction_count"], 3)

        expected_keys = {
            "source",
            "date",
            "account_id",
            "description",
            "amount",
            "original_amount",
            "direction",
            "direction_raw",
            "status",
            "balance_after",
            "counterparty",
            "metadata",
        }
        for transaction in result["transactions"]:
            self.assertEqual(set(transaction.keys()), expected_keys)

        credit_tx = next(x for x in result["transactions"] if x["source"] == "credit_card")
        self.assertEqual(credit_tx["amount"], {"value": "1234.5", "currency": "TWD"})
        self.assertEqual(credit_tx["original_amount"], {"value": "40", "currency": "USD"})

        twd_tx = next(x for x in result["transactions"] if x["source"] == "twd_account")
        self.assertEqual(twd_tx["direction"], "debit")
        self.assertEqual(twd_tx["counterparty"]["account_id"], "9876****0123")


if __name__ == "__main__":
    unittest.main()

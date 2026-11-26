"""Read-only card statement queries and installment projections (HTTP only)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from esun_bank.schema import money


_INSTALLMENT = re.compile(r"^(.*?)\s*分\s*(\d{1,2})\s*期之第\s*(\d{1,2})\s*期")
_REMAINING = re.compile(r"未到期分期金額\s*([\d,]+)\s*元")


def previous_period(period: str, offset: int) -> str:
    if (not re.fullmatch(r"20\d{4}", period) or not 1 <= int(period[4:]) <= 12
            or offset < 0):
        raise ValueError("Invalid statement month")
    index = int(period[:4]) * 12 + int(period[4:]) - 1 - offset
    year, month = divmod(index, 12)
    return f"{year:04d}{month + 1:02d}"


def collect_statements(card: Any, *, months: int = 6) -> dict[str, Any]:
    """Fetch N billed periods within one already-authenticated card session."""
    if not 1 <= months <= 12:
        raise ValueError("statement-months must be between 1 and 12")
    latest = card.fetch_bill("latest").get("lastBillYearMonth")
    previous_period(latest, 0)
    statements = []
    for index in range(months):
        period = previous_period(latest, index)
        detail = card.fetch_bill("detail", period=period)
        summary = card.fetch_bill("summary", period=period)
        bill = summary["billInfo"]
        info = bill.get("billTotalInfoList") or []
        charges = []
        for group in detail["transList"]:
            for entry in group.get("transDetailList") or []:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("merchantName")
                amount = entry.get("paymentAmount")
                charges.append({
                    "merchant": name,
                    "amount": money(amount, entry.get("paymentCurrency")),
                    "transaction_month_day": entry.get("transMonthDay"),
                    "posting_month_day": entry.get("postingMonthDay"),
                })
        statements.append({
            "period": period,
            "bill_date": bill.get("billDate"),
            "payment_due_date": bill.get("paymentDueDate"),
            "total": [money(x.get("billTotalAmount"), x.get("billTotalCurrency")) for x in info],
            "fees_and_rewards": [{
                "title": x.get("title"),
                "amount": money(x.get("amount"), x.get("currency")),
            } for x in (summary.get("feeRewardInfoList") or [])],
            "transactions": charges,
        })
    return {"latest_period": latest, "statements": statements}


def derive_installments(statements: dict[str, Any]) -> dict[str, Any]:
    """Read bank-provided installment counters, not inferred payment schedules.

    Only the newest issued statement can confirm future outstanding charges.
    Older transactions remain as history, not current debt.
    """
    records = statements["statements"]
    result = []
    for i, statement in enumerate(records):
        items = statement["transactions"]
        for j, item in enumerate(items):
            match = _INSTALLMENT.search(item.get("merchant") or "")
            if not match:
                continue
            merchant, total, number = match.group(1).strip(), int(match.group(2)), int(match.group(3))
            if not total or number > total:
                continue
            outstanding = None
            # The bank presents its '(unbilled installments ...)' line
            # immediately after the installment entry in the bill detail.
            if j + 1 < len(items):
                note = _REMAINING.search(items[j + 1].get("merchant") or "")
                if note:
                    outstanding = note.group(1).replace(",", "")
            if i != 0 and number < total:
                state = "historical_unverified"
            elif number == total:
                state = "completed"
            elif outstanding is not None:
                state = "active_confirmed"
            else:
                state = "unverified"
            result.append({
                "merchant": merchant,
                "statement_period": statement["period"],
                "installment_number": number,
                "installment_count": total,
                "billed_amount": item["amount"],
                "unbilled_balance": (money(outstanding, "TWD") if outstanding is not None else None),
                "status": state,
            })
    return {
        "as_of_statement": statements["latest_period"],
        "active": [r for r in result if r["status"] == "active_confirmed"],
        "unverified": [r for r in result if r["status"] == "unverified"],
        "history": result,
        "disclaimer": "Only the latest issued statement confirms the unbilled balance; new purchases or installments after the statement date may not appear.",
    }

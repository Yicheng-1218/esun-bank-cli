"""Unified normalized output schema for E.SUN transaction sources."""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .session import CliError

SCHEMA_VERSION = "3.0"
SOURCE_NAMES = {
    "credit": "credit_card",
    "debit": "debit_card",
    "twd": "twd_account",
}


def one_month_range(today: date | None = None) -> tuple[date, date]:
    end = today or date.today()
    year = end.year
    month = end.month - 1
    if month == 0:
        year -= 1
        month = 12
    day = min(end.day, calendar.monthrange(year, month)[1])
    return date(year, month, day), end


def mask_number(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) < 8:
        return value
    return f"{digits[:4]}****{digits[-4:]}"


def _decimal_string(value: Any) -> str | None:
    if value is None or value == "":
        return None
    raw = str(value).replace(",", "").strip()
    try:
        number = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise CliError(f"Invalid monetary value: {value!r}") from exc
    if not number.is_finite():
        raise CliError(f"Non-finite monetary value: {value!r}")
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def money(value: Any, currency: Any) -> dict[str, Any] | None:
    amount = _decimal_string(value)
    curr = str(currency).strip() if currency not in (None, "") else None
    if amount is None and curr is None:
        return None
    return {"value": amount, "currency": curr}


def _parse_card_date(group: dict[str, Any], tx: dict[str, Any]) -> date | None:
    year_match = re.findall(r"\d{4}", str(group.get("year", "")))
    month_match = re.findall(r"\d{1,2}", str(group.get("month", "")))
    month_day = [int(x) for x in re.findall(r"\d{1,2}", str(tx.get("transMonthDay", "")))]
    if not year_match or not month_day:
        return None
    year = int(year_match[0])
    month = int(month_match[-1]) if month_match else (month_day[-2] if len(month_day) >= 2 else None)
    day = month_day[-1]
    if not month:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_twd_date(tx: dict[str, Any]) -> date | None:
    for key in ("txDate", "date"):
        value = tx.get(key)
        if not isinstance(value, str):
            continue
        raw = value.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass
        match = re.search(r"(20\d{2})[-/]?(\d{2})[-/]?(\d{2})", raw)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass
    return None


def _direction(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in {"d", "debit", "支", "支出", "轉出"}:
        return "debit"
    if text in {"c", "credit", "收", "收入", "轉入"}:
        return "credit"
    return None


def _transaction(
    *,
    source: str,
    tx_date: date | None,
    account_id: Any,
    description: Any,
    amount: dict[str, Any] | None,
    original_amount: dict[str, Any] | None,
    direction: str | None,
    direction_raw: Any,
    status: Any,
    balance_after: dict[str, Any] | None,
    counterparty: dict[str, Any] | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": source,
        "date": tx_date.isoformat() if tx_date else None,
        "account_id": mask_number(account_id),
        "description": description,
        "amount": amount,
        "original_amount": original_amount,
        "direction": direction,
        "direction_raw": direction_raw,
        "status": status,
        "balance_after": balance_after,
        "counterparty": counterparty,
        "metadata": metadata,
    }


def normalize(
    *,
    requested: list[str],
    card_payloads: dict[str, dict[str, Any]] | None = None,
    twd_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    start, end = one_month_range()
    accounts: list[dict[str, Any]] = []
    transactions: list[dict[str, Any]] = []

    card_payloads = card_payloads or {}
    for source in ("credit", "debit"):
        if source not in requested:
            continue
        payload = card_payloads.get(source) or {}
        body = payload.get("body") or {}
        cards = body.get("cardInfoList")
        groups = body.get("transList")
        if not isinstance(cards, list) or not isinstance(groups, list):
            raise CliError(f"{source} card response shape changed.")

        for card in cards:
            if not isinstance(card, dict):
                continue
            accounts.append({
                "source": SOURCE_NAMES[source],
                "kind": SOURCE_NAMES[source],
                "account_id": mask_number(card.get("cardNo")),
                "label": card.get("coBrandedName"),
                "is_primary": card.get("isPrimaryCard"),
            })

        for group in groups:
            if not isinstance(group, dict):
                continue
            details = group.get("transDetailList")
            if not isinstance(details, list):
                continue
            for tx in details:
                if not isinstance(tx, dict):
                    continue
                tx_date = _parse_card_date(group, tx)
                if tx_date and not (start <= tx_date <= end):
                    continue
                transactions.append(_transaction(
                    source=SOURCE_NAMES[source],
                    tx_date=tx_date,
                    account_id=tx.get("cardNo"),
                    description=tx.get("merchantName"),
                    amount=money(tx.get("paymentAmount"), tx.get("paymentCurrency")),
                    original_amount=money(tx.get("transAmount"), tx.get("transCurrency")),
                    direction=None,
                    direction_raw=None,
                    status=tx.get("statusName") or tx.get("status"),
                    balance_after=None,
                    counterparty=None,
                    metadata={
                        "merchant": tx.get("merchantName"),
                        "card_name": tx.get("coBrandedName"),
                    },
                ))

    if "twd" in requested:
        payload = twd_payload or {}
        body = payload.get("resultBody") or {}
        account_list = body.get("twAccountList")
        query = body.get("queryDeptTxDtlResult")
        if not isinstance(account_list, list) or not isinstance(query, dict):
            raise CliError("TWD response shape changed.")

        for account in account_list:
            if not isinstance(account, dict):
                continue
            accounts.append({
                "source": SOURCE_NAMES["twd"],
                "kind": SOURCE_NAMES["twd"],
                "account_id": mask_number(account.get("accountNo")),
                "label": account.get("accountAlias"),
                "is_primary": None,
            })

        groups = query.get("detailListData")
        if not isinstance(groups, list):
            raise CliError("TWD transaction list shape changed.")

        for group in groups:
            if not isinstance(group, dict):
                continue
            detail_info = group.get("detailInfo")
            if not isinstance(detail_info, list):
                continue
            for tx in detail_info:
                if not isinstance(tx, dict):
                    continue
                tx_date = _parse_twd_date(tx)
                if tx_date and not (start <= tx_date <= end):
                    continue
                raw_direction = tx.get("debitCredit")
                counterparty = None
                if tx.get("oppositeBankCode") or tx.get("oppositeAccount"):
                    counterparty = {
                        "bank_code": tx.get("oppositeBankCode"),
                        "account_id": mask_number(tx.get("oppositeAccount")),
                    }
                transactions.append(_transaction(
                    source=SOURCE_NAMES["twd"],
                    tx_date=tx_date,
                    account_id=tx.get("demandDeptAcc") or body.get("demandDeptAcc"),
                    description=tx.get("detailTitle") or tx.get("passbookRemark"),
                    amount=money(tx.get("amount"), tx.get("currency")),
                    original_amount=None,
                    direction=_direction(raw_direction),
                    direction_raw=raw_direction,
                    status=None,
                    balance_after=money(tx.get("balance"), tx.get("currency")),
                    counterparty=counterparty,
                    metadata={
                        "passbook_remark": tx.get("passbookRemark"),
                        "transfer_message": tx.get("transferMessage"),
                        "tx_time": tx.get("txTime"),
                    },
                ))

    transactions.sort(key=lambda item: item.get("date") or "", reverse=True)
    counts = {
        SOURCE_NAMES[source]: sum(1 for tx in transactions if tx["source"] == SOURCE_NAMES[source])
        for source in requested
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "requested_sources": [SOURCE_NAMES[source] for source in requested],
        "accounts": accounts,
        "transactions": transactions,
        "summary": {
            "account_count": len(accounts),
            "transaction_count": len(transactions),
            "transactions_by_source": counts,
        },
    }

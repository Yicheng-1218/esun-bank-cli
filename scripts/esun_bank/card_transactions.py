"""信用卡消費明細查詢命令。"""

import argparse
from typing import Any

from playwright.async_api import Frame

from .output import mask_account
from .session import run_with_login


CREDIT_CARD_TRANSACTIONS_TITLE = "信用卡消費明細查詢"


def parse_money(value: str) -> dict[str, str | None]:
    """將金額文字拆成幣別與金額。"""

    parts = value.split(maxsplit=1)
    if len(parts) == 2:
        return {"currency": parts[0], "amount": parts[1]}
    return {"currency": None, "amount": value}


async def extract_card_transactions(frame: Frame) -> dict[str, Any]:
    """解析信用卡消費明細查詢結果。"""

    rows = await frame.evaluate(
        """
        () => {
          const clean = text => (text || '').replace(/\\s+/g, ' ').trim();
          const tables = [...document.querySelectorAll('table')];
          const summaryTable = tables.find(table =>
            clean(table.innerText).includes('查詢期間') &&
            clean(table.innerText).includes('排序方式')
          );
          const detailTable = tables.find(table =>
            clean(table.innerText).includes('消費日期') &&
            clean(table.innerText).includes('商店已請款明細') &&
            clean(table.innerText).includes('繳款幣別/金額')
          );
          if (!detailTable) throw new Error('credit card transaction table not found');

          const tableRows = table => [...table.querySelectorAll('tr')].map(tr =>
            [...tr.querySelectorAll('th,td')].map(td => clean(td.innerText))
          ).filter(row => row.length);

          return {
            summaryRows: summaryTable ? tableRows(summaryTable) : [],
            detailRows: tableRows(detailTable)
          };
        }
        """
    )

    summary = {row[0]: row[1] for row in rows["summaryRows"] if len(row) >= 2}
    transactions = []
    subtotals = {}
    for row in rows["detailRows"][1:]:
        if row and row[0]:
            transactions.append(
                {
                    "date": row[0],
                    "description": row[1],
                    "original_amount": parse_money(row[2]),
                    "payment_amount": parse_money(row[3]),
                    "card_number": row[4],
                    "status": row[5],
                }
            )
            continue

        if len(row) >= 4 and row[1] and row[3]:
            label = row[1].rstrip("：:")
            subtotals[label] = row[3]

    return {
        "title": CREDIT_CARD_TRANSACTIONS_TITLE,
        "query_period": summary.get("查詢期間"),
        "sort": summary.get("排序方式"),
        "transactions": transactions,
        "subtotals": subtotals,
    }


async def query_card_transactions(args: argparse.Namespace, frame: Frame) -> dict[str, Any]:
    """在已登入頁面上查詢信用卡最近一個月明細。"""

    await frame.locator("body").evaluate(
        """
        () => {
          _leftMenuLoadWidget(window.event || null, 'FCM01004', 'FCM', 'MFCM0202');
        }
        """
    )
    await frame.locator("#FCM01004").get_by_text(
        CREDIT_CARD_TRANSACTIONS_TITLE
    ).wait_for(timeout=args.timeout_ms)
    await frame.get_by_role("radio", name="最近一個月").click()
    await frame.get_by_role("link", name="查詢").click()
    await frame.get_by_text("查詢時間：").wait_for(timeout=args.timeout_ms)
    result = await extract_card_transactions(frame)

    if args.mask_accounts:
        for transaction in result["transactions"]:
            transaction["card_number"] = mask_account(transaction["card_number"])
    return result


async def run_card_transactions(args: argparse.Namespace) -> dict[str, Any]:
    """執行信用卡明細查詢命令並套用輸出遮罩選項。"""

    return await run_with_login(args, lambda frame: query_card_transactions(args, frame))

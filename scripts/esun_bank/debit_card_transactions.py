"""簽帳金融卡消費明細查詢命令。"""

import argparse
from typing import Any

from playwright.async_api import Frame

from .card_transactions import parse_money
from .output import mask_account
from .session import run_with_login


DEBIT_CARD_TRANSACTIONS_TITLE = "簽帳金融卡消費明細查詢"


async def extract_debit_card_transactions(frame: Frame) -> dict[str, Any]:
    """解析簽帳金融卡消費明細查詢結果。"""

    rows = await frame.evaluate(
        """
        () => {
          const clean = text => (text || '').replace(/\\s+/g, ' ').trim();
          const tables = [...document.querySelectorAll('table')];
          const summaryTable = tables.find(table =>
            clean(table.innerText).includes('查詢期間') &&
            clean(table.innerText).includes('排序方式')
          );
          const detailTable = document.getElementById('fcm01008:grid_DataGridBody') ||
            tables.find(table =>
              clean(table.innerText).includes('消費日期') &&
              clean(table.innerText).includes('交易明細/交易國家與地區') &&
              clean(table.innerText).includes('新臺幣 金額')
            );
          if (!detailTable) throw new Error('debit card transaction table not found');

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
    for row in rows["detailRows"][1:]:
        if len(row) < 6 or not row[0]:
            continue
        transactions.append(
            {
                "date": row[0],
                "description": row[1],
                "original_amount": parse_money(row[2]),
                "twd_amount": row[3],
                "card_number": row[4],
                "status": row[5],
            }
        )

    return {
        "title": DEBIT_CARD_TRANSACTIONS_TITLE,
        "query_period": summary.get("查詢期間"),
        "sort": summary.get("排序方式"),
        "transactions": transactions,
    }


async def run_debit_card_transactions(args: argparse.Namespace) -> dict[str, Any]:
    """執行簽帳金融卡消費明細查詢命令並套用輸出遮罩選項。"""

    async def query_recent_month(frame: Frame) -> dict[str, Any]:
        await frame.locator("body").evaluate(
            """
            () => {
              _leftMenuLoadWidget(window.event || null, 'FCM01008', 'FCM', 'MFCM0602');
            }
            """
        )
        await frame.locator("#FCM01008").get_by_text(
            DEBIT_CARD_TRANSACTIONS_TITLE
        ).wait_for(timeout=args.timeout_ms)
        await frame.get_by_role("radio", name="最近一個月").click()
        await frame.get_by_role("link", name="查詢").click()
        await frame.get_by_text("查詢時間：").wait_for(timeout=args.timeout_ms)
        return await extract_debit_card_transactions(frame)

    result = await run_with_login(args, query_recent_month)

    if not args.show_full_accounts:
        for transaction in result["transactions"]:
            transaction["card_number"] = mask_account(transaction["card_number"])
    return result

"""臺幣帳戶餘額查詢命令。"""

import argparse
from typing import Any

from playwright.async_api import Frame

from .output import mask_account
from .session import CliError, run_with_login


TWD_OVERVIEW_TITLE = "臺幣帳戶總覽"


async def extract_twd_balance(frame: Frame) -> dict[str, Any]:
    """解析首頁的臺幣帳戶總覽表格。"""

    data = await frame.evaluate(
        """
        (overviewTitle) => {
          const clean = text => (text || '').replace(/\\s+/g, ' ').trim();
          const title = [...document.querySelectorAll('body *')]
            .filter(el => clean(el.innerText) === overviewTitle)
            .sort((a, b) => clean(a.innerText).length - clean(b.innerText).length)[0];
          if (!title) throw new Error(`${overviewTitle} not found`);

          let root = title.parentElement;
          let table = null;
          for (let i = 0; i < 6 && root; i += 1, root = root.parentElement) {
            table = root.querySelector('table');
            if (table) break;
          }
          if (!table) {
            const allTables = [...document.querySelectorAll('table')];
            table = allTables.find(candidate =>
              title.compareDocumentPosition(candidate) & Node.DOCUMENT_POSITION_FOLLOWING
            );
          }
          if (!table) throw new Error(`${overviewTitle} table not found`);

          const rows = [...table.querySelectorAll('tr')].map(tr =>
            [...tr.querySelectorAll('th,td')].map(td => clean(td.innerText))
          ).filter(row => row.length);

          const accounts = [];
          let total = null;
          for (const row of rows.slice(1)) {
            if (row[0] === '總計') {
              total = row[2] || null;
              continue;
            }
            if (row.length >= 3 && row[1] && row[2]) {
              const accountParts = row[1].split(' ');
              accounts.push({
                type: row[0],
                account: accountParts[0] || row[1],
                bank: accountParts.slice(1).join(' ') || null,
                balance: row[2]
              });
            }
          }

          return {
            title: overviewTitle,
            headers: rows[0] || [],
            accounts,
            total_balance: total
          };
        }
        """,
        TWD_OVERVIEW_TITLE,
    )
    if not data.get("accounts"):
        raise CliError("No Taiwan-dollar accounts found in overview table.")
    return data


async def query_balance(args: argparse.Namespace, frame: Frame) -> dict[str, Any]:
    """在已登入頁面上查詢餘額並套用輸出遮罩選項。"""

    result = await extract_twd_balance(frame)

    if not args.show_full_accounts:
        for account in result["accounts"]:
            account["account"] = mask_account(account["account"])
    return result


async def run_balance(args: argparse.Namespace) -> dict[str, Any]:
    """執行餘額查詢命令並套用輸出遮罩選項。"""

    return await run_with_login(args, lambda frame: query_balance(args, frame))

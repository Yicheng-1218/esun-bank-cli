"""信用卡帳單資訊查詢命令。"""

import argparse
from typing import Any

from playwright.async_api import Frame

from .session import CliError, run_with_login


CREDIT_CARD_BILLS_TITLE = "信用卡帳單資訊"
BILL_TABLE_SELECTOR = '[id="fcm01003:grid_DataGridBody"]'
DETAIL_TABLE_SELECTOR = '[id="fcp01003p:grid_DataGridBody"]'


async def open_card_bills_page(frame: Frame, timeout_ms: int) -> None:
    """開啟信用卡帳單資訊頁。"""

    await frame.locator("body").evaluate(
        """
        () => {
          _leftMenuLoadWidget(window.event || null, 'FCM01003', 'FCM', 'MFCM0201');
        }
        """
    )
    await frame.locator(BILL_TABLE_SELECTOR).wait_for(timeout=timeout_ms)


async def extract_card_bills(frame: Frame) -> dict[str, Any]:
    """解析信用卡帳單資訊列表。"""

    bills = await frame.evaluate(
        """
        () => {
          const clean = text => (text || '').replace(/\\s+/g, ' ').trim();
          const tableRows = table => [...table.querySelectorAll('tr')].map(tr =>
            [...tr.querySelectorAll('th,td')].map(td => clean(td.innerText))
          ).filter(row => row.length);

          const tables = [...document.querySelectorAll('table')];
          const billTable = document.getElementById('fcm01003:grid_DataGridBody') ||
            tables.find(table => {
              const text = clean(table.innerText);
              return text.includes('帳單月份') && text.includes('應繳總金額');
            });
          if (!billTable) throw new Error('credit card bill table not found');

          const rows = tableRows(billTable);
          return rows.slice(1)
            .filter(row => row.length >= 2 && row[0] && row[1])
            .map(row => ({
              statement_month: row[0],
              total_amount: row[1]
            }));
        }
        """
    )

    if not bills:
        raise CliError("No credit card bills found in bill table.")

    return {
        "title": CREDIT_CARD_BILLS_TITLE,
        "bills": bills,
    }


async def extract_card_bill_details(frame: Frame, month: str) -> dict[str, Any]:
    """點選指定帳單月份的明細，並解析明細表格。"""

    result = await frame.evaluate(
        """
        (month) => {
          const clean = text => (text || '').replace(/\\s+/g, ' ').trim();
          const tableRows = table => [...table.querySelectorAll('tr')].map(tr =>
            [...tr.querySelectorAll('th,td')].map(td => clean(td.innerText))
          ).filter(row => row.length);
          const findBillTable = () => document.getElementById('fcm01003:grid_DataGridBody') ||
            [...document.querySelectorAll('table')].find(table => {
              const text = clean(table.innerText);
              return text.includes('帳單月份') && text.includes('應繳總金額');
            });

          const billTable = findBillTable();
          if (!billTable) throw new Error('credit card bill table not found');

          const billRows = [...billTable.querySelectorAll('tr')];
          const row = billRows.slice(1).find(candidate => {
            const cells = [...candidate.querySelectorAll('th,td')].map(cell => clean(cell.innerText));
            return cells[0] === month;
          });
          if (!row) throw new Error(`credit card bill month not found: ${month}`);

          const rowCells = [...row.querySelectorAll('th,td')].map(cell => clean(cell.innerText));
          const detailControl = [...row.querySelectorAll('a,button,input[type="button"],input[type="submit"]')]
            .find(control => clean(control.innerText || control.value).includes('明細'));
          if (!detailControl) throw new Error(`credit card bill detail link not found: ${month}`);

          const controlId = detailControl.id || detailControl.name;
          if (!controlId) throw new Error(`credit card bill detail link id not found: ${month}`);

          const onclick = detailControl.getAttribute('onclick') || '';
          const statementCode = onclick.match(/prePrint\\('([^']+)'/)?.[1] || null;
          const event = {
            target: detailControl,
            currentTarget: detailControl,
            preventDefault() {},
            stopPropagation() {}
          };
          if (statementCode && window.fcm01003obj && typeof fcm01003obj.prePrint === 'function') {
            fcm01003obj.prePrint(statementCode, event);
          }

          const form = document.forms['fcm01003'];
          if (form && form[controlId]) {
            form[controlId].value = controlId;
          }
          if (typeof cmdLinkAjaxActionWidget === 'function' && window.$) {
            cmdLinkAjaxActionWidget($('#' + controlId.replace(/:/g, '\\\\:')));
          } else {
            detailControl.click();
          }
          return {
            summary: {
              statement_month: rowCells[0] || null,
              total_due: rowCells[1] || null,
              paid_amount: rowCells[2] || null
            },
            detail_control_id: controlId
          };
        }
        """,
        month,
    )

    try:
        await frame.locator(DETAIL_TABLE_SELECTOR).wait_for(timeout=10000)
    except Exception as exc:
        message = await frame.evaluate(
            """
            () => {
              const clean = text => (text || '').replace(/\\s+/g, ' ').trim();
              const errorForm = document.forms['commonerror'];
              if (errorForm) return clean(errorForm.innerText || document.body.innerText);
              return clean(document.body.innerText);
            }
            """
        )
        if message:
            raise CliError(
                f"Credit card bill detail did not load for {month}: {message}"
            ) from exc
        raise CliError(
            f"Credit card bill detail did not load for {month}."
        ) from exc
    details = await frame.evaluate(
        """
        () => {
          const clean = text => (text || '').replace(/\\s+/g, ' ').trim();
          const detailTable = document.getElementById('fcp01003p:grid_DataGridBody');
          if (!detailTable) throw new Error('credit card bill detail table not found');

          const rows = [...detailTable.querySelectorAll('tr')].map(tr =>
            [...tr.querySelectorAll('th,td')].map(td => clean(td.innerText))
          ).filter(row => row.length);

          const headers = rows[0] || [];
          const detailRows = rows.slice(1).filter(row => row.some(value => value));
          return {
            headers,
            details: detailRows.map(row => Object.fromEntries(headers.map((header, index) => [header || `column_${index + 1}`, row[index] || null])))
          };
        }
        """
    )

    return {
        "title": f"{CREDIT_CARD_BILLS_TITLE}明細",
        "statement_month": month,
        "summary": result["summary"],
        **details,
    }


async def query_card_bills(args: argparse.Namespace, frame: Frame) -> dict[str, Any]:
    """在已登入頁面上查詢信用卡帳單月份與總額。"""

    await open_card_bills_page(frame, args.timeout_ms)
    return await extract_card_bills(frame)


async def query_card_bill_details(args: argparse.Namespace, frame: Frame) -> dict[str, Any]:
    """在已登入頁面上查詢指定月份信用卡帳單明細。"""

    await open_card_bills_page(frame, args.timeout_ms)
    return await extract_card_bill_details(frame, args.month)


async def run_card_bills(args: argparse.Namespace) -> dict[str, Any]:
    """執行信用卡帳單資訊查詢命令。"""

    return await run_with_login(args, lambda frame: query_card_bills(args, frame))


async def run_card_bill_details(args: argparse.Namespace) -> dict[str, Any]:
    """執行指定月份信用卡帳單明細查詢命令。"""

    return await run_with_login(args, lambda frame: query_card_bill_details(args, frame))

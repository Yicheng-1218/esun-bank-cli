"""簽帳金融卡帳單明細查詢命令。"""

import argparse
from typing import Any

from playwright.async_api import Frame

from .output import mask_sensitive_accounts
from .session import CliError, read_debug_page_text, run_with_login


DEBIT_CARD_BILLS_TITLE = "簽帳金融卡帳單月份"
DEBIT_CARD_BILL_DETAILS_TITLE = "簽帳金融卡帳單明細查詢"
DEBIT_CARD_BILL_MONTH_SELECTOR = '[id="fcm01007:queryDate"]'
DEBIT_CARD_BILL_DETAIL_TABLE_SELECTOR = '[id="fcp01003p:grid_DataGridBody"]'


async def open_debit_card_bill_page(frame: Frame, timeout_ms: int) -> None:
    """開啟簽帳金融卡帳單明細查詢頁。"""

    await frame.locator("body").evaluate(
        """
        () => {
          _leftMenuLoadWidget(window.event || null, 'FCM01007', 'FCM', 'MFCM0601');
        }
        """
    )
    await frame.locator(DEBIT_CARD_BILL_MONTH_SELECTOR).wait_for(timeout=timeout_ms)


async def query_debit_card_bill_month(
    frame: Frame, month: str, timeout_ms: int, debug_page_text: bool = False
) -> None:
    """選取指定月份並送出查詢。"""

    found = await frame.evaluate(
        """
        (month) => {
          const select = document.getElementById('fcm01007:queryDate');
          if (!select) throw new Error('debit card bill month select not found');
          const option = [...select.options].find(candidate => candidate.value === month);
          if (!option) return false;

          select.value = month;
          select.dispatchEvent(new Event('change', { bubbles: true }));

          const link = document.getElementById('fcm01007:linkCommand1');
          if (!link) throw new Error('debit card bill query link not found');
          const event = {
            target: link,
            currentTarget: link,
            preventDefault() {},
            stopPropagation() {}
          };
          if (window.fcm01007obj && typeof fcm01007obj.prePrint === 'function') {
            fcm01007obj.prePrint(event);
          }

          document.forms['fcm01007']['fcm01007:linkCommand1'].value =
            'fcm01007:linkCommand1';
          cmdLinkAjaxActionWidget($('#fcm01007\\\\:linkCommand1'));
          return true;
        }
        """,
        month,
    )
    if not found:
        raise CliError(f"Debit card bill month not found: {month}")

    try:
        await frame.locator(DEBIT_CARD_BILL_DETAIL_TABLE_SELECTOR).wait_for(
            timeout=timeout_ms
        )
    except Exception as exc:
        message = f"Debit card bill detail did not load for {month}."
        if debug_page_text:
            page_text = await read_debug_page_text(frame)
            message = f"{message} Page text: {page_text}"
        else:
            message = (
                f"{message} Page text suppressed; re-run with --debug-page-text "
                "only on a trusted local terminal."
            )
        raise CliError(message) from exc


async def extract_debit_card_bill_details(frame: Frame, month: str) -> dict[str, Any]:
    """解析簽帳金融卡帳單明細表格。"""

    details = await frame.evaluate(
        """
        () => {
          const clean = text => (text || '').replace(/\\s+/g, ' ').trim();
          const detailTable = document.getElementById('fcp01003p:grid_DataGridBody');
          if (!detailTable) throw new Error('debit card bill detail table not found');

          const rows = [...detailTable.querySelectorAll('tr')].map(tr =>
            [...tr.querySelectorAll('th,td')].map(td => clean(td.innerText))
          ).filter(row => row.length);
          const headers = rows[0] || [];
          const detailRows = rows.slice(1).filter(row => row.some(value => value));

          const pageText = clean(document.forms['fcp01003p']?.innerText || document.body.innerText);
          const queryTime = pageText.match(/查詢時間：\\s*([^\\s]+\\s+[^\\s]+)/)?.[1] || null;
          const statementTitle = pageText.match(/(\\d+年\\d+月帳單明細)/)?.[1] || null;

          return {
            query_time: queryTime,
            statement_title: statementTitle,
            headers,
            details: detailRows.map(row => Object.fromEntries(
              headers.map((header, index) => [header || `column_${index + 1}`, row[index] || null])
            ))
          };
        }
        """
    )

    return {
        "title": DEBIT_CARD_BILL_DETAILS_TITLE,
        "statement_month": month,
        **details,
    }


async def extract_debit_card_bill_months(frame: Frame) -> list[dict[str, Any]]:
    """讀取可查詢的簽帳金融卡帳單月份。"""

    months = await frame.evaluate(
        """
        () => {
          const select = document.getElementById('fcm01007:queryDate');
          if (!select) throw new Error('debit card bill month select not found');
          return [...select.options]
            .filter(option => option.value && option.value !== 'none')
            .map(option => ({
              statement_month: option.value
            }));
        }
        """
    )
    if not months:
        raise CliError("No debit card bill months found.")
    return months


async def extract_debit_card_bill_summary(frame: Frame, month: str) -> dict[str, Any]:
    """從指定月份明細頁擷取帳單總額，不回傳交易明細。"""

    summary = await frame.evaluate(
        """
        () => {
          const clean = text => (text || '').replace(/\\s+/g, ' ').trim();
          const detailTable = document.getElementById('fcp01003p:grid_DataGridBody');
          if (!detailTable) throw new Error('debit card bill detail table not found');

          const rows = [...detailTable.querySelectorAll('tr')].map(tr =>
            [...tr.querySelectorAll('th,td')].map(td => clean(td.innerText))
          ).filter(row => row.length);
          const totalRow = rows.find(row =>
            row.some(cell => cell.includes('本期合計金額') || cell.includes('本期合計'))
          );
          if (!totalRow) return null;

          const totalAmount = [...totalRow].reverse().find(cell =>
            cell && !cell.includes('本期合計')
          ) || null;

          return {
            total_amount: totalAmount
          };
        }
        """
    )
    if not summary or not summary.get("total_amount"):
        raise CliError(f"Debit card bill total amount not found: {month}")
    return summary


async def run_debit_card_bills(args: argparse.Namespace) -> dict[str, Any]:
    """執行簽帳金融卡帳單月份與總額查詢命令。"""

    async def query_bills(frame: Frame) -> dict[str, Any]:
        await open_debit_card_bill_page(frame, args.timeout_ms)
        months = await extract_debit_card_bill_months(frame)

        bills = []
        for month in months:
            await open_debit_card_bill_page(frame, args.timeout_ms)
            await query_debit_card_bill_month(
                frame,
                month["statement_month"],
                args.timeout_ms,
                args.debug_page_text,
            )
            summary = await extract_debit_card_bill_summary(
                frame, month["statement_month"]
            )
            bills.append({**month, **summary})

        return {
            "title": DEBIT_CARD_BILLS_TITLE,
            "bills": bills,
        }

    result = await run_with_login(args, query_bills)
    if not args.show_full_accounts:
        return mask_sensitive_accounts(result)
    return result


async def run_debit_card_bill_details(args: argparse.Namespace) -> dict[str, Any]:
    """執行指定月份簽帳金融卡帳單明細查詢命令。"""

    async def query_details(frame: Frame) -> dict[str, Any]:
        await open_debit_card_bill_page(frame, args.timeout_ms)
        await query_debit_card_bill_month(
            frame, args.month, args.timeout_ms, args.debug_page_text
        )
        return await extract_debit_card_bill_details(frame, args.month)

    result = await run_with_login(args, query_details)
    if not args.show_full_accounts:
        return mask_sensitive_accounts(result)
    return result

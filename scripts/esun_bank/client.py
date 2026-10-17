"""Read-only browser-context clients for the current E.SUN web app."""
from __future__ import annotations

import asyncio
from typing import Any

from .session import CliError

CARD_SSO_URL = "https://ebank.esunbank.com.tw/esb/?sso=IESC-CARDTRANS&taskId=CCM01008"
CARD_ENDPOINTS = {
    "credit": "/GW/creditLastYear/getFilterResult",
    "debit": "/GW/debitLastYear/getFilterResult",
}
TWD_PREQUERY_MARKER = "/ctw01002/home/preQueryTWTransactionDetail"


async def fetch_card_payloads(page: Any, sources: set[str]) -> dict[str, dict[str, Any]]:
    requested = [source for source in ("credit", "debit") if source in sources]
    if not requested:
        return {}

    await page.goto(CARD_SSO_URL, wait_until="domcontentloaded", timeout=30_000)
    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        await page.wait_for_timeout(4000)

    result = await page.evaluate(
        """
        async ({requested, endpoints}) => {
          const token = sessionStorage.getItem('accessToken');
          if (!token) return {error: 'missing accessToken'};

          async function post(path) {
            const response = await fetch(path, {
              method: 'POST',
              credentials: 'include',
              headers: {
                'Content-Type': 'application/json;charset=UTF-8',
                'Authorization': 'Bearer ' + token
              },
              body: JSON.stringify({cursor: 1})
            });
            let data = null;
            try { data = await response.json(); } catch (e) {}
            return {status: response.status, data};
          }

          const out = {};
          await Promise.all(requested.map(async source => {
            out[source] = await post(endpoints[source]);
          }));
          return out;
        }
        """,
        {"requested": requested, "endpoints": CARD_ENDPOINTS},
    )

    if not isinstance(result, dict) or result.get("error"):
        raise CliError(f"Card SSO initialization failed: {result}")

    payloads: dict[str, dict[str, Any]] = {}
    for source in requested:
        item = result.get(source) or {}
        data = item.get("data") if isinstance(item, dict) else None
        if item.get("status") != 200 or not isinstance(data, dict) or not isinstance(data.get("body"), dict):
            raise CliError(f"{source} card API did not return a valid body.")
        payloads[source] = data
    return payloads


async def fetch_twd_payload(page: Any) -> dict[str, Any]:
    future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()

    async def capture(response: Any) -> None:
        if TWD_PREQUERY_MARKER not in response.url:
            return
        try:
            data = await response.json()
        except Exception:
            return
        if isinstance(data, dict) and isinstance(data.get("resultBody"), dict) and not future.done():
            future.set_result(data)

    def on_response(response: Any) -> None:
        asyncio.create_task(capture(response))

    page.on("response", on_response)
    try:
        await page.wait_for_function("typeof window.goMibTask === 'function'", timeout=15_000)
        await page.evaluate("window.goMibTask('ctw01002-tw-home')")
        try:
            return await asyncio.wait_for(future, timeout=15)
        except asyncio.TimeoutError as exc:
            raise CliError("TWD transaction API did not respond.") from exc
    finally:
        page.remove_listener("response", on_response)

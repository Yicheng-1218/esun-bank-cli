#!/usr/bin/env python3
"""Unauthenticated, read-only E.SUN HTTP bootstrap feasibility probe.

No credentials, login attempts, browser, persisted cookies, or raw bank payloads.
This is intentionally separate from the production Playwright-based CLI.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE_URL = "https://ebank.esunbank.com.tw"
INIT_PATH = "/esb/mib-auth-portal/cpo08/cpo08001/home/init"
TAIPEI = timezone(timedelta(hours=8))


def make_envelope(now: datetime | None = None) -> bytes:
    local_time = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    return json.dumps(
        {
            "header": {
                "txnTime": local_time.strftime("%Y-%m-%d %H:%M:%S"),
                "txnFlowToken": "",
            },
            "requestBody": {},
        }
    ).encode("utf-8")


def probe(timeout: int = 20) -> dict[str, object]:
    cookies = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookies)
    )

    # Bootstrap the anonymous, in-memory cookie jar.
    client.open(
        urllib.request.Request(
            BASE_URL + "/esb/", headers={"User-Agent": "Mozilla/5.0"}
        ),
        timeout=timeout,
    ).close()

    request = urllib.request.Request(
        BASE_URL + INIT_PATH,
        data=make_envelope(),
        method="POST",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": BASE_URL,
            "Referer": BASE_URL + "/esb/",
        },
    )

    with client.open(request, timeout=timeout) as response:
        status = response.status
        payload = json.loads(response.read(128_000))

    # Whitelist metadata only. Never print or persist payload values, key
    # material, token values, cookies, or server response bodies.
    body = payload.get("resultBody") if isinstance(payload, dict) else None
    params = body.get("encryptParam") if isinstance(body, dict) else None
    return {
        "http_status": status,
        "result_code": payload.get("resultCode") if isinstance(payload, dict) else None,
        "cookie_names": sorted({cookie.name for cookie in cookies}),
        "encryption_parameter_names": sorted(params) if isinstance(params, dict) else [],
        "browser_used": False,
        "credentials_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    try:
        result = probe(timeout=args.timeout)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        # Avoid leaking any response payload in the exception text.
        print(f"probe failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["http_status"] == 200 and result["result_code"] == "0000" else 2


if __name__ == "__main__":
    raise SystemExit(main())

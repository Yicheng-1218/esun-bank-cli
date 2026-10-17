#!/usr/bin/env python3
"""Read-only E.SUN Bank browser API CLI."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from esun_bank.client import fetch_card_payloads, fetch_twd_payload
from esun_bank.schema import normalize
from esun_bank.session import (
    DEFAULT_LOCK_FILE,
    CliError,
    SessionLock,
    login,
    logout,
)

SOURCE_CHOICES = ("credit", "debit", "twd")


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--credentials-file",
        help=(
            "Private JSON file with id, user, password. "
            "Default: ~/.hermes/esun-bank/credentials.json"
        ),
    )
    parser.add_argument(
        "--force-login",
        action="store_true",
        help="Replace an existing E.SUN login session if the bank prompts for confirmation.",
    )
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    parser.add_argument(
        "--lock-file",
        default=str(DEFAULT_LOCK_FILE),
        help="Cross-process session lock path.",
    )
    parser.add_argument(
        "--lock-timeout-ms",
        type=int,
        default=120_000,
        help="How long to wait for another CLI process to release the bank session lock.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print traceback on failure.",
    )
    parser.add_argument(
        "--prompt-missing",
        action="store_true",
        help="Prompt locally for missing credentials.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only E.SUN Bank browser API CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("credit", "Query recent one-month credit-card transactions"),
        ("debit", "Query recent one-month debit-card transactions"),
        ("twd", "Query recent one-month TWD account transactions"),
        ("all", "Query all supported sources in one login session"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        add_common_options(cmd)

    batch = sub.add_parser(
        "batch",
        help="Query any combination of supported sources in one login session",
    )
    add_common_options(batch)
    batch.add_argument(
        "sources",
        nargs="+",
        choices=SOURCE_CHOICES,
        help="Any subset of: credit debit twd",
    )
    return parser


def resolve_sources(args: argparse.Namespace) -> list[str]:
    if args.command == "all":
        return ["twd", "credit", "debit"]
    if args.command == "batch":
        requested = set(args.sources)
        return [source for source in ("twd", "credit", "debit") if source in requested]
    return [args.command]


async def execute(args: argparse.Namespace) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    requested = resolve_sources(args)
    lock = SessionLock(Path(args.lock_file), args.lock_timeout_ms)

    async with lock:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            page.set_default_timeout(min(args.timeout_ms, 10_000))
            logged_in = False

            try:
                await login(page, args)
                logged_in = True

                twd_payload = None
                card_payloads: dict[str, dict[str, Any]] = {}

                # TWD first. Card SSO switches origin to iesc.esunbank.com and
                # returning to the ESB SPA is less reliable than querying ESB first.
                if "twd" in requested:
                    twd_payload = await fetch_twd_payload(page)

                card_sources = {source for source in requested if source in {"credit", "debit"}}
                if card_sources:
                    card_page = await page.context.new_page()
                    try:
                        card_payloads = await fetch_card_payloads(card_page, card_sources)
                    finally:
                        await card_page.close()

                return normalize(
                    requested=requested,
                    card_payloads=card_payloads,
                    twd_payload=twd_payload,
                )
            finally:
                if logged_in:
                    try:
                        await logout(page)
                    except Exception:
                        pass
                await context.close()
                await browser.close()


async def async_main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.timeout_ms < 1:
        parser.error("--timeout-ms must be positive")
    if args.lock_timeout_ms < 1:
        parser.error("--lock-timeout-ms must be positive")

    try:
        result = await execute(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return 2
    except Exception:
        print("error: command failed. Re-run with --debug for details.", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return 1


def main() -> int:
    return asyncio.run(async_main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""E.SUN read-only CLI using one pure-HTTP session and a short-lived private cache."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

from esun_bank.http_card import CardHttp, CardProtocolError
from esun_bank.http_protocol import EsunHttp, HttpProtocolError
from esun_bank.schema import normalize
from esun_bank.session import DEFAULT_LOCK_FILE, CliError, SessionLock, load_credentials
from esun_bank.statements import collect_statements, derive_installments

BANK_ORIGIN = "https://ebank.esunbank.com.tw"
SOURCES = ("twd", "credit", "debit")
EXTRAS = ("statements", "installments")
ALL_CHOICES = SOURCES + EXTRAS
MAX_CARD_PAGES = 4
CACHE_DIR = Path("~/.hermes/esun-bank/cache").expanduser()
TAIPEI = timezone(timedelta(hours=8))


class CardAdapter(Protocol):
    def bootstrap_from_handoff(
        self, *, redirect_url: str, token: str, bank_sso_return: Any = None
    ) -> None: ...
    def fetch(self, source: str, *, cursor: int = 1) -> dict[str, Any]: ...
    def fetch_bill(self, kind: str, *, period: str | None = None) -> dict[str, Any]: ...
    def clear(self) -> None: ...


def select_sources(command: str, specified: list[str] | None = None) -> list[str]:
    if command in ("all", "full"):
        return list(SOURCES)
    if command == "batch":
        if not specified or any(s not in ALL_CHOICES for s in specified):
            raise ValueError("Unknown or missing batch source")
        return [s for s in SOURCES if s in specified]
    if command in SOURCES:
        return [command]
    if command in EXTRAS:
        return []
    raise ValueError("Unknown command")


def select_extras(command: str, specified: list[str] | None = None) -> list[str]:
    if command == "full":
        return list(EXTRAS)
    if command in EXTRAS:
        return [command]
    if command == "batch":
        return [s for s in EXTRAS if s in (specified or [])]
    return []


def resolve_sources(args: argparse.Namespace) -> list[str]:
    return select_sources(args.command, getattr(args, "sources", None))


def collect_card_pages(card: CardAdapter, source: str, *, max_pages: int = 1) -> dict[str, Any]:
    if source not in ("credit", "debit") or not isinstance(max_pages, int) or not 1 <= max_pages <= 4:
        raise ValueError("Invalid card paging")
    cards, groups = [], []
    seen = set()
    cursor = 1
    for index in range(max_pages):
        body = card.fetch(source, cursor=cursor)["body"]
        for item in body["cardInfoList"]:
            number = item.get("cardNo") if isinstance(item, dict) else None
            if number is None or number not in seen:
                cards.append(item)
                if number is not None:
                    seen.add(number)
        batch = body["transList"]
        groups.extend(batch)
        if not batch or not any(g["transDetailList"] for g in batch):
            break
        if index + 1 < max_pages:
            if body.get("cursor") != cursor or isinstance(body.get("cursor"), bool):
                raise CardProtocolError("Card pagination cursor inconsistent")
            cursor += 1
    return {"body": {"cardInfoList": cards, "transList": groups}}


def collect_sources(
    bank: EsunHttp,
    card: CardAdapter | None,
    requested: list[str],
    *,
    bill_card: CardAdapter | None = None,
    card_pages: int = 1,
    months: int = 1,
    extras: list[str] | None = None,
    statement_months: int = 6,
) -> dict[str, Any]:
    extras = extras or []
    twd = bank.query_twd() if "twd" in requested else None
    card_payloads: dict[str, dict[str, Any]] = {}
    if any(s in requested for s in ("credit", "debit")):
        if card is None:
            raise ValueError("Card HTTP session required")
        handoff = bank.card_sso_handoff(purpose="transactions")
        card.bootstrap_from_handoff(
            redirect_url=handoff.redirect_url,
            token=handoff.token,
            bank_sso_return=lambda sid, token: bank.finish_card_sso_return(
                session_id=sid, token=token
            ),
        )
        for source in ("credit", "debit"):
            if source in requested:
                card_payloads[source] = collect_card_pages(card, source, max_pages=card_pages)

    result = normalize(
        requested=requested,
        card_payloads=card_payloads,
        twd_payload=twd,
        months=months,
    )
    if extras:
        card_for_bills = bill_card or card
        if card_for_bills is None or (card_for_bills is card and any(s in requested for s in ("credit", "debit"))):
            raise ValueError("Separate card-bill session required")
        handoff = bank.card_sso_handoff(purpose="statements")
        card_for_bills.bootstrap_from_handoff(
            redirect_url=handoff.redirect_url,
            token=handoff.token,
            bank_sso_return=lambda sid, token: bank.finish_card_sso_return(
                session_id=sid, token=token
            ),
        )
        bills = collect_statements(card_for_bills, months=statement_months)
        if "statements" in extras:
            result["statements"] = bills
        if "installments" in extras:
            result["installments"] = derive_installments(bills)
        result["statement_coverage"] = {
            "months": statement_months,
            "note": "Issued statements only; pending transactions after the last statement are excluded.",
        }
    return result


def _cache_key(args: argparse.Namespace, credentials: dict[str, str]) -> str:
    payload = {
        "version": 1,
        "day": datetime.now(TAIPEI).date().isoformat(),
        "sources": resolve_sources(args),
        "extras": select_extras(args.command, getattr(args, "sources", None)),
        "months": args.months,
        "pages": args.card_pages,
        "statement_months": args.statement_months,
        "credential_fingerprint": hashlib.sha256(
            json.dumps(credentials, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _check_cache_directory(*, create: bool = False) -> bool:
    if CACHE_DIR.is_symlink():
        raise CliError("Private cache directory must not be a symlink")
    if create:
        CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not CACHE_DIR.is_dir():
        return False
    if os.name == "posix":
        info = CACHE_DIR.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise CliError("Private cache directory permissions must be 0700")
    return True


def read_cache(key: str, ttl_seconds: int) -> dict[str, Any] | None:
    if not _check_cache_directory():
        return None
    file = CACHE_DIR / (key + ".json")
    if file.is_symlink() or not file.is_file():
        return None
    if os.name == "posix":
        info = file.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise CliError("Private cache file permissions must be 0600")
    try:
        stored = json.loads(file.read_text(encoding="utf-8"))
        if (stored.get("version") == 1 and 0 <= time.time() - stored["at"] <= ttl_seconds
                and isinstance(stored.get("payload"), dict)):
            return stored["payload"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def write_cache(key: str, payload: dict[str, Any]) -> None:
    _check_cache_directory(create=True)
    fd, temp_path = tempfile.mkstemp(dir=CACHE_DIR, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "at": time.time(), "payload": payload}, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, CACHE_DIR / (key + ".json"))
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pure HTTP, read-only E.SUN Bank CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in (*ALL_CHOICES, "all", "full", "batch"):
        cmd = sub.add_parser(command)
        if command == "batch":
            cmd.add_argument("sources", nargs="+", choices=ALL_CHOICES)
        cmd.add_argument("--confirm-live", action="store_true",
                         help="Authorize one non-forced login if private cache is absent or expired")
        cmd.add_argument("--cached-only", action="store_true",
                         help="Never contact the bank; fail if no fresh private cache exists")
        cmd.add_argument("--fresh", action="store_true",
                         help="Bypass the cache and require a new authorized bank session")
        cmd.add_argument("--months", type=int, default=1,
                         help="Rolling history period for cards/TWD (1..11 months)")
        cmd.add_argument("--card-pages", type=int, default=1,
                         help="Card transaction pages per source (1..4)")
        cmd.add_argument("--statement-months", type=int, default=6,
                         help="Latest issued credit-card statements (1..12)")
        cmd.add_argument("--cache-minutes", type=int, default=15,
                         help="Private normalized-response cache lifetime (default 15)")
        cmd.add_argument("--credentials-file")
        cmd.add_argument("--prompt-missing", action="store_true")
        cmd.add_argument("--timeout-ms", type=int, default=30_000)
        cmd.add_argument("--lock-file", default=str(DEFAULT_LOCK_FILE))
        cmd.add_argument("--lock-timeout-ms", type=int, default=120_000)
    return parser


async def execute(args: argparse.Namespace) -> dict[str, Any]:
    if not 1 <= args.months <= 11 or not 1 <= args.card_pages <= 4 or not 1 <= args.statement_months <= 12:
        raise CliError("Invalid date range or card page count")
    if args.cache_minutes < 0 or args.timeout_ms <= 0 or args.lock_timeout_ms <= 0:
        raise CliError("Invalid timeout or cache configuration")
    if args.fresh and args.cached_only:
        raise CliError("Cannot combine --fresh and --cached-only")
    # Read the existing private credentials to scope cache entries to this
    # account. Cached queries still never contact the bank or trigger login.
    credentials = load_credentials(args)
    key = _cache_key(args, credentials)
    requested = resolve_sources(args)
    extras = select_extras(args.command, getattr(args, "sources", None))
    async with SessionLock(Path(args.lock_file), args.lock_timeout_ms):
        if not args.fresh and args.cache_minutes > 0:
            cached = read_cache(key, args.cache_minutes * 60)
            if cached is not None:
                cached["request"] = {"transport": "httpx", "mode": "local_cache", "bank_logins": 0}
                return cached
        if args.cached_only:
            raise CliError("No valid cached response for these options")
        if not args.confirm_live:
            raise CliError("No login attempted; use --confirm-live to authorize")
        timeout = httpx.Timeout(args.timeout_ms / 1000)
        with (
            httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as bank_http,
            httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as card_http,
            httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as bill_http,
        ):
            bank = EsunHttp(bank_http, origin=BANK_ORIGIN)
            card = CardHttp(card_http)
            bill_card = CardHttp(bill_http)
            try:
                bank.initialize()
                bank.submit_nonforced_login(
                    user_id=credentials["id"], username=credentials["user"],
                    password=credentials["password"]
                )
                bank.confirm_session()
                result = collect_sources(
                    bank, card, requested, bill_card=bill_card, card_pages=args.card_pages,
                    months=args.months, extras=extras,
                    statement_months=args.statement_months,
                )
            finally:
                try:
                    if bank.login_accepted:
                        bank.logout()
                finally:
                    card.clear()
                    bill_card.clear()
                    card_http.cookies.clear()
                    bill_http.cookies.clear()
                    bank_http.cookies.clear()
        result["request"] = {"transport": "httpx", "mode": "bank_live", "bank_logins": 1}
        if args.cache_minutes > 0:
            write_cache(key, result)
        return result


async def async_main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = await execute(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (CliError, HttpProtocolError, CardProtocolError, ValueError):
        print("error: Read-only query failed or private cache unavailable; no bank data printed.",
              file=sys.stderr)
        return 2
    except Exception:
        print("error: Read-only query failed; no bank data printed.", file=sys.stderr)
        return 1


def main() -> int:
    return asyncio.run(async_main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""CLI helpers for E.SUN Bank internet banking automation."""

import argparse
import asyncio
import sys
from typing import Any, Awaitable, Callable

from esun_bank.balance import run_balance
from esun_bank.card_bills import run_card_bill_details, run_card_bills
from esun_bank.card_transactions import run_card_transactions
from esun_bank.output import write_output
from esun_bank.session import DEFAULT_URL, ENV_ID, ENV_PASSWORD, ENV_USER, CliError

CommandRunner = Callable[[argparse.Namespace], Awaitable[dict[str, Any]]]


def add_common_options(command: argparse.ArgumentParser, mask_help: str) -> None:
    """為子命令加入登入、瀏覽器與輸出相關共用參數。"""

    command.add_argument("--url", default=DEFAULT_URL)
    command.add_argument("--id", help=f"Login ID. Prefer {ENV_ID}.")
    command.add_argument("--user", help=f"Login user name. Prefer {ENV_USER}.")
    command.add_argument(
        "--password", help=f"Login password. Prefer {ENV_PASSWORD}.")
    command.add_argument(
        "--credentials-file",
        help="Local JSON file with id, user, password. Defaults to skill-dir credentials.json when present.",
    )
    command.add_argument("--prompt-missing", action="store_true",
                         help="Prompt for missing credentials.")
    command.add_argument("--headed", "--head", action="store_true",
                         help="Show browser window. Default is headless.")
    command.add_argument("--keep-open", action="store_true",
                         help="Keep browser open after command.")
    command.add_argument("--timeout-ms", type=int, default=30000)
    command.add_argument("--output", choices=["json", "text"], default="json")
    command.add_argument("--mask-accounts", action="store_true", help=mask_help)


def build_parser() -> argparse.ArgumentParser:
    """建立 CLI 參數解析器。"""

    parser = argparse.ArgumentParser(
        description="E.SUN Bank internet banking CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    balance = subparsers.add_parser(
        "balance", help="Get Taiwan-dollar account balances")
    add_common_options(balance, "Mask account numbers in output.")

    card_transactions = subparsers.add_parser(
        "card-transactions", help="Get recent-month credit card transactions")
    add_common_options(card_transactions, "Mask card numbers in output.")

    card_bills = subparsers.add_parser(
        "card-bills", help="Get credit card bill months and total due amounts")
    add_common_options(card_bills, "Mask account numbers in output.")

    card_bill_details = subparsers.add_parser(
        "card-bill-details", help="Get details for one credit card bill month")
    add_common_options(card_bill_details, "Mask account numbers in output.")
    card_bill_details.add_argument(
        "--month", required=True, help="Bill month to open, for example 0115/04.")
    return parser


COMMAND_RUNNERS: dict[str, CommandRunner] = {
    "balance": run_balance,
    "card-bill-details": run_card_bill_details,
    "card-bills": run_card_bills,
    "card-transactions": run_card_transactions,
}


async def async_main(argv: list[str]) -> int:
    """解析命令列參數、派發子命令並處理 CLI 錯誤。"""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        runner = COMMAND_RUNNERS.get(args.command)
        if not runner:
            raise CliError(f"Unknown command: {args.command}")
        result = await runner(args)
        write_output(result, args.output)
        return 0
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def main() -> int:
    """同步入口點。"""

    return asyncio.run(async_main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())

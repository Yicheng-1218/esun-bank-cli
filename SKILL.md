---
name: esun-bank-cli
description: Use this skill when Codex needs to automate E.SUN Bank personal internet banking through the bundled Python CLI, including opening the login page, signing in, reading Taiwan-dollar balances, and querying recent credit-card transaction details. Requires Python and Playwright to be installed, including browser binaries. Credentials must be available to the CLI through environment variables or an explicit local credentials file in the skill directory; never hard-code real credentials in prompts or source files.
---

# 玉山銀行 CLI

Use the bundled Python CLI for E.SUN Bank automation instead of re-creating browser steps manually.

## Requirements

- Python 3.10+
- Playwright for Python
- Browser binaries installed with `python -m playwright install chromium`
- Credentials supplied at runtime

Install prerequisites on Linux, macOS, or Windows Git Bash:

```bash
bash setup.sh
```

For Windows PowerShell users, use Git Bash to run `setup.sh` or ask Codex to translate the setup script to PowerShell.

Manual install:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

The Python CLI uses Python Playwright for saved automation.

## Credentials

The CLI loads credentials in this order:

1. `--credentials-file <path>` when explicitly provided
2. `credentials.json` next to `SKILL.md`
3. Environment variables

Use `credentials.json` in the skill directory when you want automatic discovery:

```json
{
  "id": "身分證字號或統一編號",
  "user": "使用者名稱",
  "password": "使用者密碼"
}
```

Expected path:

```bash
~/.codex/skills/esun-bank-cli/credentials.json
```

Use environment variables when no credentials file exists:

```bash
ESUN_ID=...
ESUN_USER=...
ESUN_PASSWORD=...
```

Do not store real credentials in `SKILL.md` or committed source. If using a credentials file, keep it local and pass it with `--credentials-file`.

## CLI

Script:

```bash
python scripts/esun_bank_cli.py balance
python scripts/esun_bank_cli.py card-bills
python scripts/esun_bank_cli.py card-bill-details --month 0115/04
python scripts/esun_bank_cli.py card-transactions
```

Useful options:

```bash
python scripts/esun_bank_cli.py balance --headed
python scripts/esun_bank_cli.py balance --credentials-file credentials.json
python scripts/esun_bank_cli.py balance --output text
python scripts/esun_bank_cli.py card-bills --output text
python scripts/esun_bank_cli.py card-bill-details --month 0115/04 --output text
python scripts/esun_bank_cli.py card-transactions --mask-accounts
```

Default mode is headless. Use `--headed` only when the user asks to see the browser.
Each command attempts to log out before the browser is closed or the process exits.

The `balance` command:

1. Opens `https://ebank.esunbank.com.tw/index.jsp`
2. Fills the ID, user name, and password fields
3. Clicks login
4. Waits for `臺幣帳戶總覽`
5. Extracts Taiwan-dollar account rows and total balance
6. Prints JSON by default

The `card-transactions` command:

1. Logs in with the same credential loading rules
2. Opens the credit-card transaction query page
3. Selects `最近一個月`
4. Clicks `查詢`
5. Extracts query period, sort mode, transaction rows, and subtotals
6. Prints JSON by default

The `card-bills` command:

1. Logs in with the same credential loading rules
2. Opens the credit-card bill information page
3. Extracts bill months and total due amounts
4. Prints JSON by default

The `card-bill-details` command:

1. Logs in with the same credential loading rules
2. Opens the credit-card bill information page
3. Finds the requested bill month
4. Clicks that row's detail link
5. Extracts the detail table headers and rows
6. Prints JSON by default

## Safety

- Do not echo passwords or full credential sets in chat.
- Do not write credentials into the skill source.
- When reporting results, mask account numbers unless the user explicitly asks for full local output.

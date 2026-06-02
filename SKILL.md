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
- Credentials supplied at runtime on a trusted local machine only

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
2. `credentials.json` next to `SKILL.md` for personal local use only
3. Environment variables

Do not place real credentials in a skill directory that will be zipped or shared. If you use a local credentials file, copy `credentials.example.json` and keep the real file private:

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

Do not store real credentials in `SKILL.md`, committed source, prompts, command-line arguments, or logs. The CLI does not support `--password`; use `ESUN_PASSWORD`, a private credentials file, or `--prompt-missing`. On Linux/macOS the credentials file must not be group/world-readable; use `chmod 600 credentials.json`. Before sharing a folder, run `find . -name "credentials.json" -o -name "*.env"`.

## CLI

Script:

```bash
python scripts/esun_bank_cli.py balance
python scripts/esun_bank_cli.py credit-card-bills
python scripts/esun_bank_cli.py credit-card-bill-details --month 0115/04
python scripts/esun_bank_cli.py credit-card-transactions
python scripts/esun_bank_cli.py debit-card-bill-details --month 115/04
python scripts/esun_bank_cli.py debit-card-bills
python scripts/esun_bank_cli.py debit-card-transactions
```

Useful options:

```bash
python scripts/esun_bank_cli.py balance --headed
python scripts/esun_bank_cli.py balance --credentials-file credentials.json
python scripts/esun_bank_cli.py balance --output text
python scripts/esun_bank_cli.py credit-card-bills --output text
python scripts/esun_bank_cli.py credit-card-bill-details --month 0115/04 --output text
python scripts/esun_bank_cli.py credit-card-transactions --show-full-accounts
python scripts/esun_bank_cli.py debit-card-bill-details --month 115/04 --output text
python scripts/esun_bank_cli.py debit-card-bills --output text
python scripts/esun_bank_cli.py debit-card-transactions --show-full-accounts
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

The `credit-card-transactions` command:

1. Logs in with the same credential loading rules
2. Opens the credit-card transaction query page
3. Selects `最近一個月`
4. Clicks `查詢`
5. Extracts query period, sort mode, transaction rows, and subtotals
6. Prints JSON by default

The `credit-card-bills` command:

1. Logs in with the same credential loading rules
2. Opens the credit-card bill information page
3. Extracts bill months and total amounts
4. Prints JSON by default

The `credit-card-bill-details` command:

1. Logs in with the same credential loading rules
2. Opens the credit-card bill information page
3. Finds the requested bill month
4. Clicks that row's detail link
5. Extracts the detail table headers and rows
6. Prints JSON by default

The `debit-card-transactions` command:

1. Logs in with the same credential loading rules
2. Opens the debit-card transaction query page
3. Selects `最近一個月`
4. Clicks `查詢`
5. Extracts query period, sort mode, and transaction rows
6. Prints JSON by default

The `debit-card-bill-details` command:

1. Logs in with the same credential loading rules
2. Opens the debit-card bill detail query page
3. Selects the requested bill month
4. Clicks `查詢`
5. Extracts the bill detail table headers and rows
6. Prints JSON by default

The `debit-card-bills` command:

1. Logs in with the same credential loading rules
2. Opens the debit-card bill detail query page
3. Reads the available bill months
4. Queries each month
5. Extracts each bill's total amount without returning transaction details
6. Prints JSON by default

## Safety

- Do not echo passwords or full credential sets in chat.
- Do not write credentials into the skill source.
- Account and card numbers are masked by default. Never add `--show-full-accounts` unless the user explicitly asks for full local output on a trusted terminal. Do not run this skill in cloud sandboxes, CI, remote containers, or untrusted hosts. This is not an official E.SUN Bank tool; users assume the risk of automating real internet banking. The CLI pins the E.SUN login URL and refuses non-E.SUN HTTPS hosts. By default, errors suppress logged-in page text; only use `--debug-page-text` for trusted local debugging because it may expose account or transaction data.

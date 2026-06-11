# Security Policy

This is an unofficial local automation helper for E.SUN Bank internet banking. It handles real banking credentials and account, card, bill, and transaction data.

## Safe Use

- Run only on a trusted local machine.
- Do not run in cloud sandboxes, CI, remote containers, or shared hosts.
- Do not put real credentials in prompts, source files, command-line arguments, logs, screenshots, or shared archives.
- Prefer environment variables, `--prompt-missing`, or a private `--credentials-file` with owner-only permissions.
- On Linux/macOS, use `chmod 600 credentials.json` for any credentials file.
- Account and card numbers are masked by default. Use `--show-full-accounts` only when you explicitly need full local output on a trusted terminal.
- `--debug-page-text` may expose logged-in page content. Use it only for trusted local debugging.

## Before Sharing This Skill

Run this check from the repository or skill directory and remove any real secrets before packaging:

```bash
find . -name "credentials.json" -o -name "*.env"
```

## Reporting a Vulnerability

Please report issues privately to the maintainer of the copy of this skill you are using. Include:

- The affected command or workflow.
- The expected safe behavior.
- The observed unsafe behavior.
- Minimal reproduction steps that do not include real credentials or account data.

Do not include real IDs, user names, passwords, account numbers, card numbers, bills, or transaction details in reports.

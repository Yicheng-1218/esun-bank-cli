---
name: esun-bank-cli
description: Use for read-only E.SUN Bank transaction queries: recent credit-card, debit-card, and TWD account transactions. Browser-authenticated API client with unified schema and single-session batch support.
metadata:
  version: "3.0.0"
---

# 玉山銀行 Browser API CLI

這份 skill 已完成 v3 breaking rewrite。

舊版 iframe / DOM scraper、balance / bills / statement-month commands 不再是正式能力。不要重新走舊 selector。

## Credential

所有 Hermes profile 共用唯一 credential：

```text
~/.hermes/esun-bank/credentials.json
```

來源優先順序：

1. `--credentials-file`
2. `ESUN_CREDENTIALS_FILE`
3. `~/.hermes/esun-bank/credentials.json`
4. `ESUN_ID` / `ESUN_USER` / `ESUN_PASSWORD`

不得讀出、顯示或複製 credential 值。

## Commands

```bash
bash "$SKILL_DIR/scripts/run.sh" credit
bash "$SKILL_DIR/scripts/run.sh" debit
bash "$SKILL_DIR/scripts/run.sh" twd
bash "$SKILL_DIR/scripts/run.sh" all
bash "$SKILL_DIR/scripts/run.sh" batch twd credit
bash "$SKILL_DIR/scripts/run.sh" batch credit debit
```

所有 command 都是 read-only query。

`all` 與 `batch` 只登入一次。

## Existing bank session

預設不搶既有 session。

如果銀行顯示「確定登入」：

- 沒有 `--force-login` → CLI 停止
- 有 `--force-login` → 才確認取代既有 session

不要自動加 `--force-login`。

## Unified schema

所有 command 都輸出 v3 envelope：

- `schema_version = "3.0"`
- `period`
- `requested_sources`
- `accounts[]`
- `transactions[]`
- `summary`

每筆 transaction 都有相同 keys：

- `source`
- `date`
- `account_id`
- `description`
- `amount`
- `original_amount`
- `direction`
- `direction_raw`
- `status`
- `balance_after`
- `counterparty`
- `metadata`

source：

- `credit_card`
- `debit_card`
- `twd_account`

金額統一：

```json
{"value": "1234.5", "currency": "TWD"}
```

未知或不適用欄位使用 null，不用 0 猜值。

## Session lifecycle

CLI 必須保留：

1. cross-process lock
2. explicit browser context
3. ESB primary tab login once
4. TWD query on the primary ESB tab
5. credit/debit query in a secondary card-SSO tab sharing the same context
6. close the card tab
7. normalize all requested sources
8. finally perform the two-step header logout on the original ESB tab
9. wait until 「重新登入」 is visible
10. close context / Chromium
11. release lock

即使 query exception，也要執行 cleanup。

## 禁止能力

不可新增或呼叫：

- 轉帳
- 繳款
- 受款人管理
- 卡片管理
- 密碼 / credential 變更
- 任何資金或設定 mutation

## Implementation

正式實作：

- `scripts/esun_bank/session.py`
- `scripts/esun_bank/client.py`
- `scripts/esun_bank/schema.py`
- `scripts/esun_bank_cli.py`

舊 module filenames 若仍存在，只是 migration tombstone，不是可用 API。

# esun-bank-cli

玉山個人網銀的唯讀 Browser API CLI。

這個 repository 已在 2026-09-29 進行 breaking rewrite。舊版 iframe / DOM scraper、帳單查詢與相容 schema 不再是正式實作；目前只保留三個需求：

- 近一月信用卡消費紀錄
- 近一月簽帳金融卡消費紀錄
- 近一月臺幣帳戶交易明細

## 架構

登入仍由 Playwright 操作玉山新版網銀登入頁。登入成功後，不再逐頁 scrape 交易表格，而是沿用 browser session 呼叫網站自己的 JSON API。

### 信用卡 / 簽帳卡

1. 登入玉山個人網銀。
2. 進入卡片 SSO。
3. 從 browser session 取得短效 access token。
4. Browser-context fetch：
   - credit: `/GW/creditLastYear/getFilterResult`
   - debit: `/GW/debitLastYear/getFilterResult`
5. 正規化成共同 transaction schema，只保留近一月。

### 臺幣帳戶

1. 登入後呼叫網站既有 `goMibTask('ctw01002-tw-home')`。
2. 接收交易明細 JSON response。
3. 正規化成共同 transaction schema，只保留近一月。

## Credential

只保留一份 account-level credential：

```text
~/.hermes/esun-bank/credentials.json
```

所有 Hermes profile 共用它。

預設 precedence：

1. `--credentials-file`
2. `ESUN_CREDENTIALS_FILE`
3. `~/.hermes/esun-bank/credentials.json`
4. `ESUN_ID` / `ESUN_USER` / `ESUN_PASSWORD`

credential file 在 POSIX 必須是 `600`。

## CLI

先 setup：

```bash
bash setup.sh
```

單一來源：

```bash
bash scripts/run.sh credit
bash scripts/run.sh debit
bash scripts/run.sh twd
```

全部一次查：

```bash
bash scripts/run.sh all
```

任意 batch：

```bash
bash scripts/run.sh batch twd credit
bash scripts/run.sh batch credit debit
```

batch / all 都只登入一次。

若玉山偵測到已有登入 session，預設停止，不自行搶 session。只有你明確要取代時：

```bash
bash scripts/run.sh all --force-login
```

## 統一輸出

所有 command 都輸出相同 envelope：

```json
{
  "schema_version": "3.0",
  "period": {
    "start": "YYYY-MM-DD",
    "end": "YYYY-MM-DD"
  },
  "requested_sources": [
    "twd_account",
    "credit_card",
    "debit_card"
  ],
  "accounts": [],
  "transactions": [],
  "summary": {
    "account_count": 0,
    "transaction_count": 0,
    "transactions_by_source": {}
  }
}
```

每筆 transaction 都使用同一組欄位：

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

帳號與卡號預設遮罩。

## Session lifecycle

每次 command：

```text
acquire process lock
  → launch Chromium + explicit browser context
  → ESB 主 tab login once
  → TWD query on ESB 主 tab
  → card query on a secondary SSO tab in the same context
  → close card tab
  → normalize output
  → finally: ESB 主 tab header logout + confirm
  → wait until 「重新登入」
  → close context / Chromium
  → release lock
```

即使查詢中途丟 exception，也會走 `finally` 嘗試 logout 並關閉 browser。

## 安全邊界

- read-only query only
- 不實作轉帳、繳款、卡片設定、受款人維護或帳戶設定
- 不輸出 credential
- 不輸出 Authorization token
- 不把 raw banking payload / HAR commit 進 repo
- 跨 process lock 避免兩個 CLI 同時登入同一帳號

## 驗證

VPS headless Chromium 曾實測完整 `all` 成功：

- 臺幣帳戶 1 個
- 近一月臺幣交易 41 筆
- 信用卡 2 張
- 近一月信用卡交易 22 筆
- 簽帳金融卡 1 張
- 近一月簽帳交易 21 筆

資料筆數會隨實際交易變動。

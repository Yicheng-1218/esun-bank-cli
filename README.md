# esun-bank-cli

玉山個人網銀的唯讀 Browser API CLI。

目前維護 v3 API 實作，只提供三種交易查詢：

- 近一月信用卡消費紀錄
- 近一月簽帳金融卡消費紀錄
- 近一月臺幣帳戶交易明細

## 架構

由 Playwright 操作玉山網銀登入頁，登入後透過同一個 browser context 使用網站既有的 JSON API，不依賴交易表格 DOM。**目前不是純 HTTP CLI：登入、SSO token、TWD response 監聽及登出仍依賴 Playwright / Chromium。** 舊版 iframe / DOM scraper 與帳單、餘額等指令已移除。

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

憑證檔案選擇順序：

1. `--credentials-file`
2. `ESUN_CREDENTIALS_FILE`
3. `~/.hermes/esun-bank/credentials.json`
如果選定的憑證檔案缺少欄位，會以 `ESUN_ID` / `ESUN_USER` / `ESUN_PASSWORD` 補足；如果沒有選定任何憑證檔案，也可以只使用這三個環境變數。指定檔案不存在時會報錯，不會偷偷改用其他檔案。

credential file 在 POSIX 必須是 `600`。請參考 `credentials.example.json` 的欄位格式，但不要把真實憑證放入 repository。

## CLI

需要 Python 3.10+、Bash 與可安裝 Chromium 的執行環境。依賴列於 `requirements.txt`（目前是 Playwright）；`setup.sh` 會安裝 Python 套件及 Chromium。第一次使用先執行：

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
    "transactions_by_source": {
      "twd_account": 0,
      "credit_card": 0,
      "debit_card": 0
    }
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

`period` 是以執行當天向前推一個日曆月（例如 10/18 到 9/18），而不是固定 30 天。能解析日期的交易才會依 `period` 篩選；來源資料缺少可解析日期時，該筆交易仍會保留且 `date` 為 `null`，不代表已確認在期間內。

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
  → best-effort wait for 「重新登入」
  → close context / Chromium
  → release lock
```

即使查詢中途發生 exception，也會走 `finally` 嘗試 logout 並關閉 browser。銀行端登出屬 best-effort，不保證網路中斷時一定成功。

## 安全邊界

- read-only query only
- 不實作轉帳、繳款、卡片設定、受款人維護或帳戶設定
- 不輸出 credential
- 不輸出 Authorization token
- 不把 raw banking payload / HAR commit 進 repo
- 跨 process lock 避免兩個 CLI 同時登入同一帳號

## 離線驗證

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
bash -n setup.sh scripts/run.sh
bash scripts/run.sh --help
```

離線測試只涵蓋 CLI 參數、資料正規化與憑證安全契約，不會登入銀行。實際網銀 API 可能改版，需另外以授權的測試環境確認。

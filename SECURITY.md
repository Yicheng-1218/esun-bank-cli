# Security

## Credential

正式 credential 只放：

```text
~/.hermes/esun-bank/credentials.json
```

所有 Hermes profile 共用，不再建立 profile-specific bank credential。

POSIX：

- credential parent directory: 建議 `700`
- credential file: 必須 `600`

CLI 也接受顯式 `--credentials-file` / `ESUN_CREDENTIALS_FILE` 覆寫。

禁止：

- credential 放進 repository
- credential 值輸出到 log / prompt / HAR
- Authorization token 寫入 disk
- raw banking payload commit 到 Git

臨時網銀偵錯輸出應留在 repository 之外的私人目錄（或忽略的 `tmp/`），不要提交 HAR、完整交易明細或 token/cookie。範例憑證僅供說明欄位，不得填入真實資料。

正規化回應快取儲存在 `~/.hermes/esun-bank/cache`，目錄 `0700`、檔案 `0600`；不可儲存 session、原始銀行 payload 或密碼。預設 15 分鐘後不再使用舊快取，舊檔可能仍留在磁碟直到另行清理，不得將此誤稱為定時刪除。

## Bank session

銀行登入不是「零副作用」：登入會建立 / 取代 server-side session。

因此：

- 本機 CLI 使用 cross-process lock
- 預設不登入：必須明確使用 `--confirm-live` 才能建立新的網銀 session
- 遇到 existing session 就停止，不支援 `--force-login` 或自動重試
- `full`、`batch`、`all` 共用一次非強制 ESB 登入
- 以 HTTPX 分別保存 ESB、CARDTRANS、CARDBILL 的短效 cookie jar/Bearer，無瀏覽器
- 正常或 exception 都 best-effort 呼叫 ESB 登出，清空全部短效 session 與 cookie jar
- 關閉全部 HTTP clients、釋放跨程序 lock
- 快取命中、或 `--cached-only` 命中時不連線銀行，也不觸發登入通知

## Read-only boundary

這個 repository 只允許讀取：

- credit-card transactions
- debit-card transactions
- TWD account transactions
- issued credit-card statements and summaries
- installments observable in issued statements

不實作任何資金或帳戶設定 mutation。

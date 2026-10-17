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

## Bank session

銀行登入不是「零副作用」：登入會建立 / 取代 server-side session。

因此：

- 本機 CLI 使用 cross-process lock
- 預設遇到 existing session 就停止
- 只有 `--force-login` 才取代銀行既有 session
- batch / all 只登入一次
- ESB 主 tab 保留到最後；卡片 SSO 使用同 context 的獨立 tab
- 正常或 exception 都 best-effort 執行 header「登出」→「立即登出」
- 等待「重新登入」出現後才關閉 browser context
- 最後一定 close Chromium 並釋放 process lock

## Read-only boundary

這個 repository 只允許讀取：

- credit-card transactions
- debit-card transactions
- TWD account transactions

不實作任何資金或帳戶設定 mutation。

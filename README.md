# 玉山銀行 CLI Skill

這是一個給 Agent 使用的自訂 skill，透過 Python Playwright 自動操作玉山銀行個人網路銀行，提供帳戶餘額查詢、信用卡帳單查詢、信用卡交易查詢與簽帳金融卡交易查詢的 CLI 工具。

## 功能

- 登入玉山銀行個人網路銀行
- 查詢臺幣帳戶總覽與總餘額
- 查詢信用卡帳單月份與總額
- 查詢最近一個月信用卡交易明細
- 查詢最近一個月簽帳金融卡交易明細
- 支援 JSON 與純文字輸出
- 預設遮蔽帳號或卡號輸出；只有明確使用 `--show-full-accounts` 才顯示完整號碼
- 可透過環境變數或明確指定的本機憑證檔提供登入資訊

## 專案結構

```text
.
├── SKILL.md              # skill 入口與操作指引
├── agents/openai.yaml    # Codex 顯示名稱與預設提示
├── scripts/              # Python CLI 與銀行自動化流程
├── requirements.txt      # Python 套件需求
├── credentials.example.json # 憑證檔範例，請勿填入真實資料後分享
├── setup.sh              # 安裝依賴與 Playwright Chromium
├── SECURITY.md           # 安全使用與漏洞回報指南
└── LICENSE
```

## 安裝

需求：

- Python 3.10+
- Playwright for Python
- Playwright Chromium browser binaries

安裝依賴：

```bash
bash setup.sh
```

或手動安裝：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

## 憑證設定

CLI 會依序讀取：

1. `--credentials-file <path>`
2. skill 目錄旁的 `credentials.json`（僅供個人本機使用，不建議放進準備分享的 skill 目錄）
3. 環境變數

CLI 不接受 `--password`，避免密碼出現在 shell history、process list、CI log 或 Agent trace。Linux/macOS 上，憑證檔若可被 group/world 讀取會被拒絕；請使用 `chmod 600 credentials.json`。

可複製 `credentials.example.json` 建立本機 `credentials.json`，格式如下：

```json
{
  "id": "身分證字號或統一編號",
  "user": "使用者名稱",
  "password": "使用者密碼"
}
```

也可以使用環境變數：

```bash
ESUN_ID=...
ESUN_USER=...
ESUN_PASSWORD=...
```

請勿將真實憑證提交到 Git。此專案的 `.gitignore` 已排除 `credentials.json`、`*.local.json` 與 `*.env`。如果要壓縮或分享資料夾，請先檢查是否誤包憑證：

```bash
find . -name "credentials.json" -o -name "*.env"
```

## 使用方式

查詢臺幣帳戶餘額：

```bash
python scripts/esun_bank_cli.py balance
```

查詢最近一個月信用卡交易：

```bash
python scripts/esun_bank_cli.py credit-card-transactions
```

查詢最近一個月簽帳金融卡交易：

```bash
python scripts/esun_bank_cli.py debit-card-transactions
```

查詢指定月份簽帳金融卡帳單明細：

```bash
python scripts/esun_bank_cli.py debit-card-bill-details --month 115/04
```

查詢簽帳金融卡帳單月份與總額：

```bash
python scripts/esun_bank_cli.py debit-card-bills
```

查詢信用卡帳單月份與應繳總金額：

```bash
python scripts/esun_bank_cli.py credit-card-bills
```

查詢指定月份信用卡帳單明細：

```bash
python scripts/esun_bank_cli.py credit-card-bill-details --month 0115/04
```

常用選項：

```bash
python scripts/esun_bank_cli.py balance --output text
python scripts/esun_bank_cli.py balance --headed
python scripts/esun_bank_cli.py balance --credentials-file credentials.json
python scripts/esun_bank_cli.py credit-card-bills --output text
python scripts/esun_bank_cli.py credit-card-bill-details --month 0115/04 --output text
python scripts/esun_bank_cli.py credit-card-transactions --show-full-accounts
python scripts/esun_bank_cli.py debit-card-transactions --show-full-accounts
python scripts/esun_bank_cli.py debit-card-bills --output text
python scripts/esun_bank_cli.py debit-card-bill-details --month 115/04 --output text
```

預設為 headless 模式。只有在需要看見瀏覽器操作時才使用 `--headed`。

## 安全注意事項

- 這不是玉山銀行官方工具；會自動操作真實網銀頁面，使用者需自行承擔網銀自動化風險。
- 只能在可信任的本機環境執行；不要在雲端 sandbox、CI、遠端容器或不受信任主機執行。
- 不要在聊天內容、README、SKILL.md、原始碼、命令列參數或 log 中寫入真實密碼。
- CLI 已固定使用 `https://ebank.esunbank.com.tw/index.jsp`，並拒絕把憑證送往非玉山網銀 HTTPS host。
- 帳號與卡號預設遮蔽；只有在可信任本機終端機且使用者明確需要時，才使用 `--show-full-accounts`。
- 預設錯誤訊息不輸出登入後頁面全文；`--debug-page-text` 可能暴露敏感帳務資料，只能在可信任本機除錯時使用。
- 詳細安全使用與漏洞回報方式請見 `SECURITY.md`。
- 使用完畢後，CLI 會嘗試登出並關閉瀏覽器。

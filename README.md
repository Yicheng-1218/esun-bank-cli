# 玉山銀行 CLI Skill

這是一個給 Agent 使用的自訂 skill，透過 Python Playwright 自動操作玉山銀行個人網路銀行，提供帳戶餘額查詢、信用卡帳單查詢與最近一個月信用卡交易查詢的 CLI 工具。

## 功能

- 登入玉山銀行個人網路銀行
- 查詢臺幣帳戶總覽與總餘額
- 查詢信用卡帳單月份與應繳總金額
- 查詢最近一個月信用卡交易明細
- 支援 JSON 與純文字輸出
- 支援遮蔽帳號或卡號輸出
- 可透過環境變數或本機 `credentials.json` 提供登入資訊

## 專案結構

```text
.
├── SKILL.md              # skill 入口與操作指引
├── agents/openai.yaml    # Codex 顯示名稱與預設提示
├── scripts/              # Python CLI 與銀行自動化流程
├── requirements.txt      # Python 套件需求
├── setup.sh              # 安裝依賴與 Playwright Chromium
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
2. skill 目錄旁的 `credentials.json`
3. 環境變數

`credentials.json` 格式：

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

請勿將真實憑證提交到 Git。此專案的 `.gitignore` 已排除 `credentials.json`、`*.local.json` 與 `*.env`。

## 使用方式

查詢臺幣帳戶餘額：

```bash
python scripts/esun_bank_cli.py balance
```

查詢最近一個月信用卡交易：

```bash
python scripts/esun_bank_cli.py card-transactions
```

查詢信用卡帳單月份與應繳總金額：

```bash
python scripts/esun_bank_cli.py card-bills
```

查詢指定月份信用卡帳單明細：

```bash
python scripts/esun_bank_cli.py card-bill-details --month 0115/04
```

常用選項：

```bash
python scripts/esun_bank_cli.py balance --output text
python scripts/esun_bank_cli.py balance --headed
python scripts/esun_bank_cli.py balance --credentials-file credentials.json
python scripts/esun_bank_cli.py card-bills --output text
python scripts/esun_bank_cli.py card-bill-details --month 0115/04 --output text
python scripts/esun_bank_cli.py card-transactions --mask-accounts
```

預設為 headless 模式。只有在需要看見瀏覽器操作時才使用 `--headed`。

## 安全注意事項

- 不要在聊天內容、README、SKILL.md 或原始碼中寫入真實密碼。
- 對外分享查詢結果時，建議使用 `--mask-accounts`。
- 使用完畢後，CLI 會嘗試登出並關閉瀏覽器。
- 此工具會操作真實網銀頁面，執行前請確認是在可信任的本機環境。

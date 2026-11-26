# E.SUN Bank CLI｜玉山銀行 CLI

讓你的個人銀行資料走進終端機與 AI Agent。

一個以 Python 開發的非官方、唯讀玉山銀行 CLI，讓你不用手動登入網銀、逐筆複製交易紀錄，就能取得信用卡、簽帳金融卡、臺幣帳戶及帳單資料，並用於記帳、消費分析與個人財務管理。

可獨立使用，也提供 [Agent Skill](SKILL.md)，讓支援 Skills 的 AI Agent 協助你分析自己的財務資料。

## 特色

- **純 HTTP**：使用 HTTPX，不需要 Playwright、Chromium 或背景瀏覽器。
- **批次查詢**：多種資料來源共用一次網銀登入，減少重複登入與通知。
- **本地快取**：預設 15 分鐘內可重用相同查詢的結果，無須再次連線銀行。
- **結構化資料**：統一輸出 JSON，方便與 Python、記帳工具及 AI Agent 整合。
- **唯讀與隱私**：不支援轉帳、繳款或帳戶設定；即時登入需要明確授權，不強制登入、不繞過驗證。

## 支援功能

| 功能 | 說明 | 指令 |
| --- | --- | --- |
| 信用卡 | 歷史刷卡紀錄 | `credit` |
| 簽帳金融卡 | 歷史消費紀錄 | `debit` |
| 臺幣帳戶 | 帳戶交易紀錄 | `twd` |
| 信用卡帳單 | 已出帳明細、金額、費用及回饋 | `statements` |
| 分期付款 | 依已出帳帳單判讀期數及明示的未到期金額 | `installments` |
| 整合查詢 | 查詢三種交易來源 | `all` |
| 完整查詢 | 交易、帳單與分期 | `full` |
| 自訂批次 | 選擇需要的資料來源 | `batch` |

## 可以拿來做什麼？

- 分析每月信用卡與簽帳金融卡的消費趨勢。
- 找出訂閱服務、固定開支與一次性大額消費。
- 整理信用卡帳單、分期負擔與現金流。
- 將交易資料串接到自己的記帳程式或財務分析工具。
- 透過 AI Agent 用自然語言詢問個人財務問題。

CLI 負責取得資料；消費分類、預算與財務推估可由使用者或 Agent 進一步分析。

## 安裝

需求：Python 3.10+、Git、Bash（Linux / macOS / WSL）。

```bash
git clone https://github.com/Yicheng-1218/esun-bank-cli.git
cd esun-bank-cli
bash setup.sh
```

首次使用請建立私有憑證檔。已有設定者不需重新建立。

```bash
umask 077
mkdir -p "$HOME/.hermes/esun-bank"
chmod 700 "$HOME/.hermes/esun-bank"
cp -n credentials.example.json "$HOME/.hermes/esun-bank/credentials.json"
chmod 600 "$HOME/.hermes/esun-bank/credentials.json"
```

使用本地編輯器填入自己的網銀身分證字號（或統一編號）、使用者名稱及密碼。也可以用 `--credentials-file` 指定其他私有憑證檔。

請勿將真實憑證放進 repository、貼到聊天視窗或上傳至 GitHub。

## 快速開始

```bash
# 查看可用參數，不會登入銀行
bash scripts/run.sh full --help

# 查詢信用卡與簽帳金融卡近六個月交易，最多各兩頁
bash scripts/run.sh batch credit debit --months 6 --card-pages 2 --confirm-live

# 查詢交易、近六期已出帳帳單與分期
bash scripts/run.sh full --months 6 --card-pages 2 --statement-months 6 --confirm-live

# 重用上述完整查詢的快取，不連線銀行
bash scripts/run.sh full --months 6 --card-pages 2 --statement-months 6 --cached-only
```

`--confirm-live` 允許快取未命中時進行一次非強制登入；`--cached-only` 則只讀本地快取。快取需使用相同的資料來源及查詢參數。完整參數可透過各指令的 `--help` 查看。

## 搭配 AI Agent 使用

本專案內附 [SKILL.md](SKILL.md)，可安裝至支援 Agent Skills 的工具，例如 Codex、Hermes Agent。

1. 將 repository clone 到 Agent 可讀取的位置，執行 `bash setup.sh`。
2. 依使用中的 Agent 安裝方式，將此 repository 註冊為 Skill（保留 `SKILL.md` 與 CLI 程式）。
3. 將 Skill 範例中的 `SKILL_DIR` 設為實際安裝路徑，完成上述私有憑證設定。
4. 重新載入 Skill，即可請 Agent 協助查詢與分析。

也可以直接將此 GitHub repository 連結交給具有終端機操作能力的 Agent，請它依照 README 與 SKILL.md 安裝。憑證仍由自己在本地設定。

### 問問你的 Agent

> 幫我分析過去半年的信用卡與簽帳金融卡消費，區分固定開支、日常消費與一次性支出。

> 幫我整理目前帳單中仍在分期的項目，以及可以確認的剩餘未到期金額。

> 根據我的固定開支，估算如果休息半年，需要準備多少生活費？

Agent 應優先使用快取，只有取得使用者明確授權後才即時登入，並避免重複計算信用卡消費與帳單繳款。

## 目前狀態與限制

目前版本：**v4.0.1**。

原純 HTTP 實驗版曾完成信用卡、簽帳金融卡與臺幣交易的真實整合驗證。最新版 CLI 與新增帳單功能已通過離線測試，但尚未完成新版真實銀行端到端驗證。

- 未出帳交易尚未支援。
- 查詢月份與頁數是篩選及請求上限，不保證銀行回傳完整歷史資料。
- 分期結果僅依已出帳資料判讀，不應視為完整負債清單。
- 本地快取仍包含敏感財務資料，請妥善保管；快取逾期不代表檔案已刪除。
- 銀行介面更新可能導致功能暫時失效。

## 免責聲明

本專案為非官方開源個人工具，與玉山銀行無任何隸屬、合作或授權關係。

僅供本人或經合法授權的帳戶進行唯讀查詢。使用前請確認銀行服務條款、相關規範及自身資訊安全需求。登入可能觸發銀行安全通知；遇到多因素驗證、驗證碼或登入衝突時，請勿嘗試繞過。

本工具不保證資料的即時性、正確性、完整性或服務可用性，亦不提供金融或投資建議。請以銀行官方紀錄為準，並自行評估使用風險。軟體依授權條款按現狀提供。

## 相關文件

[Agent Skill](SKILL.md) · [安全規範](SECURITY.md) · [JSON 輸出規格](references/output-contract.md) · [授權條款](LICENSE)

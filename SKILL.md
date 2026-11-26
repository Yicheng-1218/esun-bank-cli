---
name: esun-bank-cli
description: "查詢使用者本人玉山銀行（E.SUN）信用卡、簽帳金融卡、臺幣帳戶交易、歷史帳單及分期；純 HTTPX、一次登入 Batch、私有短期快取。適用消費統計、固定開支、現金流、分期與裸辭生活費試算。只能唯讀。"
metadata:
  version: "4.0.2"
---

# 玉山銀行 CLI 使用指引（HTTPX 唯讀版）

**唯一正式執行入口**：此 skill repository 的 `scripts/run.sh`。既有 VPS 安裝預設位於 `~/agent-workspace/shared-agent-resources/skills/esun-bank-cli`；其他環境請將下方 `SKILL_DIR` 設為實際 checkout 路徑。
不需要 Playwright／Chromium；**禁止執行**舊 `agent-workspace/esun-bank-cli/scripts/probe_*.py`、`login_new.py` 或重新手工打造瀏覽器登入流程。

## 1. 先判斷需不需要登入

1. 讀取使用者問題，確定資料來源、期間、是否需要帳單與分期。
2. 同一次問題一律**優先整合為一個 `full` 或 `batch`**。不可以為每張卡、每個月份、每個細項各自重新登入。
3. 若需要最新銀行資料，**先嘗試 `--cached-only`**，參數必須與第一次快照一致。找不到相符快取，才評估是否使用者已明確要求即時銀行查詢。
4. 只有使用者明確授權向玉山查詢時才能使用 `--confirm-live`。未授權則停下詢問，**不能直接重登**。不可用 `--fresh` 作為預設。
5. 一次成功查詢後，在同一回合對輸出結果做所有分類、加總、圖表與推論；**不要為分析不同角度重查**。
6. 若 `--cached-only` 未命中，原本的即時授權也不代表可以反覆登入；同一需求以一個登入工作階段為原則。

## 2. 選擇正確指令

| 使用者意圖 | 指令 | 需要注意 |
|---|---|---|
| 信用卡刷卡消費 | `credit` | 預設近 1 個月、1 頁 |
| 簽帳金融卡消費 | `debit` | 與信用卡分開統計 |
| 臺幣活存進出／扣款 | `twd` | 可能回傳不足請求期間的資料 |
| 信用卡帳單／繳款日／費用與回饋 | `statements` | 僅已出帳月份 |
| 仍在分期／剩餘未到期金額 | `installments` | 僅能根據最新已出帳帳單驗證 |
| 三種交易一起查 | `all` | 一次登入，不查帳單 |
| 完整收支＋帳單＋分期 | `full` | 財務分析**首選** |
| 指定其中幾種資料 | `batch SOURCE...` | 減少不必要 API |

安裝只需一次：`bash "$SKILL_DIR/setup.sh"`。執行前確認 `scripts/run.sh`、正式 README 與 SECURITY.md，勿用舊研究目錄 Python 腳本。

## 3. 推薦指令（最少登入）

```bash
SKILL_DIR="$HOME/agent-workspace/shared-agent-resources/skills/esun-bank-cli"

# 先用快取（完全不發送銀行請求，不會觸發銀行登入通知）
bash "$SKILL_DIR/scripts/run.sh" full \
  --months 6 --card-pages 2 --statement-months 6 --cached-only

# 使用者已明確要求即時銀行查詢，快取又不存在或過期，才使用
bash "$SKILL_DIR/scripts/run.sh" full \
  --months 6 --card-pages 2 --statement-months 6 --confirm-live

# 只需卡片消費：不查帳單，減少 SSO/API 流量
bash "$SKILL_DIR/scripts/run.sh" batch credit debit \
  --months 6 --card-pages 2 --confirm-live

# 日常最近一個月三種交易
bash "$SKILL_DIR/scripts/run.sh" all --confirm-live

# 查看指令與限制，不會登入
bash "$SKILL_DIR/scripts/run.sh" full --help
```

**注意：**快取鍵包含查詢來源、參數、日期與帳戶憑證雜湊。從 `full` 改成單獨 `installments` **不會自動命中**。預設快取有效 15 分鐘，過期不會使用，舊檔不會背景自動刪除。需要確保完全不連線請用 `--cached-only`；`--fresh` 只供使用者明確要求刷新時使用，不能與 `--cached-only` 並用。

## 4. 各項資料的定義與財務分析守則

- `credit/debit`：交易日與實際入帳／付款金額。注意退刷、外幣、請款與跨頁重複，不能直接將所有正值當成淨消費。
- `twd`：帳戶入金、出金、扣款。**信用卡帳單繳款不是額外消費**，和信用卡交易合併時應去重；轉帳／投資／存款移動不一定是生活開銷。
- `statements`：已結帳的帳單與利息回饋；不要將同一交易的「刷卡金額」與「帳單總額」相加。
- `installments.active`：僅是**最新已出帳帳單有銀行明示未到期金額**的分期；`history` 是歷史付款，不代表仍應繳；`unverified` 與未出帳交易都不得被推定結清。
- `--months 6` 只設定本地篩選範圍，**不保證**銀行回傳完整 6 個月；`--card-pages 2` 最多抓兩頁，不是自動查到六個月。評估期間完整性後，必要時在下次已授權查詢增加頁數（最多 4），不要無限制嘗試。
- 裸辭與現金流推估應區分固定扣款、必要生活費、單次事件、分期剩餘未到期餘額、信用卡已刷待繳、未來旅行與備用金；保留「確定／推估／未涵蓋」標示。
- **永不填補**銀行未回傳的交易、期數、金額；結果不足時明確告訴使用者缺口，不可宣稱已查到所有帳單。

## 5. 安全、隱私與錯誤處理

- **唯讀**：不得實作轉帳、繳款、受款人管理、帳戶卡片設定、修改憑證或其他資金／設定異動。
- 銀行登入並非零副作用：可能產生通知或影響原 Session。CLI 只提供非強制登入；遇到 Session 衝突、MFA、驗證碼立即停止，**不可繞過**。
- 憑證僅使用 `~/.config/esun-bank-cli/credentials.json`（0600）或明確指定私有路徑，不要讀出、顯示、複製帳密；不可輸出 Authorization、Cookie、Token、原始銀行 response。
- 私有正規化快取：`~/.cache/esun-bank-cli/`，目錄 0700、檔案 0600。快取仍包含**敏感的金額、交易摘要／備註**，不要貼出整份 JSON、上傳到 Git、或存到公開路徑；對話只呈現必要加總、遮罩與分析。
- CLI 失敗時不重試登入，不自行切回 Playwright、不編寫新的銀行 API 探勘腳本。只呈報固定錯誤與可驗證的診斷步驟；必要時請使用者決定是否另行查詢。
- 不進行無必要的銀行實測，離線測試用合成資料與 MockTransport，不使用真實憑證。

## 6. 技術路徑與驗證狀態

```text
CLI → 本地快取/跨程序鎖
    → HTTPX ESB 匿名初始化、RSA 加密、非強制登入（最多一次）
    → 臺幣資料（如要求）
    → CARDTRANS SSO → credit/debit 分頁（如要求）
    → CARDBILL SSO → 已結帳 statement detail/summary（如要求）
    → 正規化＋分期判讀 → 登出並清除 3 組 HTTP session → 私有快取
```

主要檔案：`scripts/esun_bank_cli.py`（命令、快取、調度），`scripts/esun_bank/http_protocol.py`（ESB／SSO），`http_card.py`（兩組卡片 API），`http_crypto.py`（RSA），`statements.py`（帳單與分期），`schema.py`（交易結構），`session.py`（憑證與鎖），`tests/`（離線測試）。

**驗證界線：**2026-11-26 正式 HTTPX 查詢流程通過真實網銀端到端測試：一次登入完成臺幣交易、信用卡及簽帳金融卡各一頁、最新一期已出帳帳單明細與摘要、分期資料結構及登出。多頁、多期及不同帳戶資料完整性未逐項驗證，不可將測試成功解讀為所有資料皆已涵蓋。

詳細路徑、參數與限制見 `README.md`，安全規範以 `SECURITY.md` 為準。

# 玉山銀行 CLI v4.0.1：唯讀、純 HTTP

正式入口只使用 Python HTTPX 與銀行前端 JSON API，不再啟動 Chromium / Playwright。支援單次網銀登入、Batch、信用卡與簽帳卡歷史分頁、臺幣交易、已結帳帳單、分期判讀與私有短期快取。

**驗證界線：**原純 HTTP 實驗版的信用卡／簽帳卡／臺幣同次登入已有先前真實檢查紀錄。這次新升級的正式入口、CARDBILL SSO 與帳單 API 已對照公開前端契約和合成資料完成離線測試，但**尚未進行升級後的真實銀行端到端驗證**。新路徑如遇銀行權限或改版，應安全停止並報錯。

本專案為非官方個人工具，與玉山銀行無隸屬關係。僅限本人或經合法授權的帳戶使用，銀行介面可能隨時改版。

## 安裝與快速開始

    git clone https://github.com/Yicheng-1218/esun-bank-cli.git
    cd esun-bank-cli
    bash setup.sh

Python 3.10+、Bash（Linux/macOS 或 WSL）；依賴 HTTPX 0.28.1 與 cryptography。既有安裝者可在原 checkout 更新後重跑 setup.sh。

建立私有憑證檔（僅首次設定；已有檔案請保留）：

    umask 077
    mkdir -p "$HOME/.hermes/esun-bank"
    chmod 700 "$HOME/.hermes/esun-bank"
    cp -n credentials.example.json "$HOME/.hermes/esun-bank/credentials.json"
    chmod 600 "$HOME/.hermes/esun-bank/credentials.json"

使用本地編輯器填入範例中的 id、user、password 欄位。不要把真實憑證寫進 Git checkout、命令列參數或對話。也可使用 --credentials-file 指定私有檔案。

先執行 `bash scripts/run.sh full --help` 確認安裝；此指令不登入銀行。

## 指令

| 指令 | 查詢內容 |
|---|---|
| credit | 信用卡歷史交易 |
| debit | 簽帳金融卡歷史交易 |
| twd | 臺幣帳戶交易（來源資料期間可能較短） |
| statements | 最新 N 期已結帳信用卡帳單，含金額、明細、費用與回饋 |
| installments | 從已結帳帳單判讀分期期數與銀行明示的未到期餘額 |
| all | 原有信用卡＋簽帳卡＋臺幣交易 |
| full | all＋statements＋installments |
| batch SOURCE... | 自選任意來源，一次網銀登入完成 |

示例：

    # 一次登入：信用卡、簽帳卡、臺幣、帳單、分期
    bash scripts/run.sh full --months 6 --card-pages 2 --statement-months 6 --confirm-live

    # 同樣的參數在快取效期內讀取本地結果，不接觸銀行
    bash scripts/run.sh full --months 6 --card-pages 2 --statement-months 6 --cached-only

    # 自選來源，同一次網銀登入
    bash scripts/run.sh batch credit debit statements installments --confirm-live

    # 不使用舊快取，重新向銀行查詢（可能觸發登入通知）
    bash scripts/run.sh full --months 6 --card-pages 2 --fresh --confirm-live

參數：

- --confirm-live：僅在需要連線時授權一次非強制網銀登入；預設**不會**登入。
- --cached-only：只用本地快取，快取不存在／過期立即停止，**絕不觸發登入**。
- --fresh：跳過現有快取，必須同時使用 --confirm-live。
- --cache-minutes N：快取有效期預設 15 分鐘，設 0 則停用。
- --months N：卡片／臺幣交易日期篩選（1～11 個日曆月），預設 1；不代表銀行一定回傳完整期間。
- --card-pages N：信用卡／簽帳卡最多查 1～4 頁（預設 1），以銀行回傳 cursor 遞增，拒絕異常游標。
- --statement-months N：已結帳信用卡帳單最多查 1～12 期，預設 6。
- --credentials-file PATH、--timeout-ms、--lock-timeout-ms：原有私有憑證與等待控制。
- **不提供 --force-login**，遇重複登入、MFA 或驗證碼便停止。

快取以**帳戶憑證雜湊、日期、來源組合及查詢參數**隔離，因此只有參數完全相同時會命中。先 full 後 installments 不會自動共用快取；要反覆分析，請延用第一次 full 的查詢參數。快取只存經遮罩的正規化資料，不含 cookie、登入權杖或密碼；放在 ~/.hermes/esun-bank/cache（目錄 0700，檔案 0600）。有效期限制重用時間，舊檔不會由背景程式定時刪除。

## 請求模式

    CLI → 帳戶專屬快取鍵 + 跨程序鎖
        ├─ 快取命中：直接輸出，銀行登入 0 次
        └─ 快取未命中且有 --confirm-live：
             HTTPX ESB 主 Client：匿名初始化／取得 RSA 公鑰
             → RSA 加密帳密 → 非強制登入 → 確認 session
             → 臺幣 API（若要求）
             → IESC-CARDTRANS SSO → 信用卡／簽帳卡游標分頁（若要求）
             → IESC-CARDBILL SSO → 已結帳帳單 detail／summary（若要求）
             → 正規化／分期判讀
             → finally HTTP 登出與清除 3 組 HTTP clients 的 cookies、Bearer
             → 本地 0600 快取 → 結果輸出

一次 full 僅有**一次網銀帳密登入**，但可能有兩個不同服務的 SSO 交換，以及多筆唯讀 GET/POST。CLI 結束不留可重用的銀行登入 Session；跨指令重用的是私有的**結果快取**。

### 實際唯讀路徑

| 系統 | 請求路徑 | 用途 |
|---|---|---|
| ESB | /esb/mib-auth-portal/cpo08/cpo08001/home/init | 初始化 |
| ESB | /esb/mib-auth-portal/cpo08/cpo08001/home/doAction | 非強制登入 |
| ESB | /esb/mib-ctw-portal/ctw01/ctw01002/home/init 與 preQueryTWTransactionDetail | 臺幣交易 |
| ESB | /esb/mib-auth-portal/common/sso/startSSOProcess | 卡片 SSO |
| CARDTRANS | /GW/creditLastYear/getFilterResult | 信用卡歷史分頁 |
| CARDTRANS | /GW/debitLastYear/getFilterResult | 簽帳卡歷史分頁 |
| CARDBILL | /GW/cardBill/getLastBillYearMonth | 最新已結帳月份 |
| CARDBILL | /GW/creditBill/getDetailResult | 帳單明細／分期期數／未到期金額 |
| CARDBILL | /GW/creditBill/getSummaryResult | 帳單金額／到期日／分期利息 |
| ESB | /esb/mib-auth-portal/cpo08/cpo08004/home/logout | 登出 |

CARDTRANS 用 IESC-CARDTRANS／CCM01008；CARDBILL 用 IESC-CARDBILL／CCM01007。兩者皆是玉山公開前端定義的服務，使用同一次網銀登入產生的 SSO handoff；不支援任意 Host 重導或新增資金變動 API。

## 輸出與限制

- 原交易回傳 schema_version=3.0、period、requested_sources、accounts、transactions、summary。
- 帳單回傳 statements（已結帳月份、費用／回饋、各筆交易）。
- 分期回傳 installments.active、unverified、history。**active 只包含最新帳單明示未到期分期金額的項目**；沒有出現在帳單不代表已結清。
- request.transport= httpx，request.mode 為 bank_live 或 local_cache，request.bank_logins 為 1 或 0。
- 臺幣 API 可能只回傳最近幾個月／數十筆；歷史卡片跨頁不保證無重覆。未出帳交易、其他銀行、現金與卡外分期不會自動納入。

## Codebase

    scripts/run.sh                     正式入口與執行環境檢查
    scripts/esun_bank_cli.py           參數、batch、HTTP session、私有快取、清理
    scripts/esun_bank/http_protocol.py ESB 純 HTTP 登入／臺幣／SSO／登出
    scripts/esun_bank/http_card.py     IESC CARDTRANS 與 CARDBILL Bearer API
    scripts/esun_bank/http_crypto.py   RSA 登入欄位加密
    scripts/esun_bank/statements.py    帳單整理與分期判讀
    scripts/esun_bank/schema.py        交易正規化、遮罩、日期篩選
    scripts/esun_bank/session.py       共同憑證與跨程序 lock
    tests/test_http_production.py      純離線 HTTP 正式入口測試
    SKILL.md                           AI Agent 操作指引與財務分析守則
    agents/openai.yaml                 Agent skill metadata
    experiments/                       歷史匿名研究程式碼，不在正式版 import chain

## Agent / Skill 整合

將 repository 放在 Agent 可讀取的位置，依其 skill 安裝方式註冊 SKILL.md，並將指引內的 SKILL_DIR 調整為實際 checkout 路徑。Hermes / Codex 可共用同一個 CLI 與私有憑證檔，不需要額外登入實作。優先以相同參數讀取快取，獲得明確即時查詢授權後才使用 --confirm-live。

## v4.0.1 更新摘要

- 正式入口由 Playwright 改為 HTTPX；移除正式瀏覽器 adapter 與相關依賴。
- 新增 full / batch、自選來源、私有短期結果快取及有界分頁。
- 新增已結帳信用卡帳單及依帳單明示餘額判讀分期。
- 保留 schema v3 交易資料與 all 的原始三來源行為；新增 request / statement_coverage 等欄位。
- 未出帳明細尚未支援；新版完整登入與帳單流程仍待真實帳戶整合驗證。

## 離線驗證（不登入銀行）

    bash -n setup.sh scripts/run.sh
    .venv/bin/python -m unittest discover -s tests -p 'test_*.py'
    bash scripts/run.sh full --help

嚴禁轉帳、繳款、卡片與帳戶設定、強制登入、繞過 MFA／驗證碼，也不能印出憑證、原始回應、Session ID、Bearer、cookie 或私密資料於錯誤訊息中。

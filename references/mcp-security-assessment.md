# Archived MCP assessment

這份檔案保留作歷史紀錄，但不再描述目前 CLI 架構。

2026-09-29 起正式實作已改為 v3 Browser API CLI：

- 只有 credit / debit / TWD transaction queries
- 所有 command 共用 unified schema v3
- 支援 single-session batch
- credential 集中在單一 account-level file
- session lifecycle 使用 process lock + login once + finally logout
- 不再維護舊 balance / bills / statement-month DOM scraper

如果未來重新做 MCP，應直接包裝 v3 的 typed read-only query interface，不要引用舊 v2 adapter 或已移除的 bills commands。

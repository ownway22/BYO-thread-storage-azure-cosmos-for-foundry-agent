# BYO Thread Storage in Foundry — Copilot 開發指引

## 專案概覽

本專案實作「Bring Your Own Thread Storage」功能，以 Azure Cosmos DB 作為 Microsoft Foundry Agent 的對話執行緒儲存體，使用 Python 開發。核心能力包含：建立對話執行緒、追加訊息、查詢歷史紀錄、刪除執行緒。

## 技術棧

- **語言**：Python 3.9+（async/await 模式）
- **SDK**：GitHub Copilot SDK（技術預覽版）
- **資料庫**：Azure Cosmos DB（NoSQL API）
- **平台**：Microsoft Foundry（AI Agent 託管）
- **規格管理**：SpecKit 工作流程

## 程式碼規範

- 遵循 `.github/instructions/python.instructions.md` 的 PEP 8 規範與型別提示要求
- 遵循 `.github/instructions/copilot-sdk-python.instructions.md` 的 SDK 使用慣例
- 使用 Google 風格 docstring、f-string、snake_case 命名
- 每行 88 字元上限，每檔 300 行上限

---

## Skills 使用指引

### 1. `git-commit` — Git 提交

**使用時機**：當使用者要求提交程式碼變更、或提到 `/commit` 時。

**觸發情境**：
- 完成一項任務後需要提交
- 使用者明確要求建立 commit
- 批次修改後需要有組織地提交

**使用要點**：
- 先分析 `git diff` 確定變更類型與範圍
- 自動判斷 Conventional Commits 的 `type`（feat、fix、docs、refactor 等）與 `scope`
- 將相關變更分組為邏輯性提交，避免一次 commit 包含不相關的修改
- 描述使用現在式祈使語氣，長度不超過 72 字元
- 引用相關 issue：`Closes #123`、`Refs #456`
- **安全守則**：絕不提交機密資訊（.env、credentials）、絕不 force push 到 main

**典型流程**：
1. `git status --porcelain` 檢查變更
2. `git diff --staged`（或 `git diff`）分析內容
3. 決定 type/scope/description
4. 執行 `git commit`

---

### 2. `github-copilot-starter` — Copilot 設定初始化

**使用時機**：當需要為新專案或新模組建立完整的 GitHub Copilot 設定結構時。

**觸發情境**：
- 建立新專案並需要 Copilot 設定
- 現有專案需要補齊 Copilot 設定檔
- 技術棧更換後需要更新設定

**使用要點**：
- 先詢問或確認技術棧、專案類型、是否使用 GitHub Actions
- 產生的檔案包含：`copilot-instructions.md`、指令檔（instructions）、技能檔（skills）、代理檔（agents）
- 優先參考 awesome-copilot 的既有模板，而非從零撰寫
- `.instructions.md` 檔案只放高階原則與慣例，不放程式碼範例

**注意事項**：本專案已有基礎設定，通常只需在新增技術元件時補充，而非全部重建。

---

### 3. `github-issues` — GitHub Issue 管理

**使用時機**：當使用者要求建立、更新、查詢或管理 GitHub Issues 時。

**觸發情境**：
- 使用者說「建立一個 issue」、「回報 bug」、「提交 feature request」
- 需要更新 issue 狀態、標籤、指派人
- 需要設定 issue 欄位（日期、優先級、自訂欄位）
- 管理 sub-issues、依賴關係、blocking/blocked-by 關聯
- 將任務轉為 GitHub Issues（搭配 `speckit.taskstoissues`）

**使用要點**：
- 讀取操作使用 MCP 工具（`mcp__github__issue_read` 等）
- 寫入操作使用 `gh api`（REST API），因為 MCP 尚不支援建立/更新
- 根據 issue 類型選用對應模板（Bug Report / Feature Request / Task）
- **優先使用 issue types 而非 labels** 進行分類（Bug、Feature、Task）
- 標題具體且可操作，不超過 72 字元

---

## Agents 使用指引

### SpecKit 系列 — 規格驅動開發工作流程

本專案使用 SpecKit 進行功能規劃與實作管理，所有規格產出物存放於 `specs/` 目錄。

| Agent | 觸發時機 | 輸出 |
|-------|---------|------|
| `speckit.specify` | 使用者描述新功能需求 | `spec.md`（功能規格） |
| `speckit.clarify` | 規格中有模糊或不足之處 | 更新 `spec.md` 中的釐清內容 |
| `speckit.plan` | 規格確認後，需要設計實作方案 | `plan.md`（實作計畫） |
| `speckit.tasks` | 計畫確認後，需要拆分可執行任務 | `tasks.md`（任務清單） |
| `speckit.implement` | 任務清單完成，開始編碼實作 | 依 tasks.md 逐項實作 |
| `speckit.analyze` | 產出物完成後，需要一致性檢查 | 跨文件品質分析報告 |
| `speckit.checklist` | 需要驗收檢核清單 | 自訂檢核清單 |
| `speckit.taskstoissues` | 將 tasks.md 轉為 GitHub Issues | 建立相依排序的 issues |
| `speckit.constitution` | 建立或更新專案開發憲章 | 專案憲章文件 |

**典型工作流程**：
```
specify → clarify → plan → tasks → implement → analyze
                                  ↘ taskstoissues（需要 issue 追蹤時）
```

**使用原則**：
- 遵守順序：先有規格，再有計畫，再有任務，最後才實作
- 每個階段確認後再進入下一階段
- `speckit.analyze` 可在任何階段使用，用來檢查文件間的一致性

---

### `GitHub Actions Expert` — CI/CD 工作流程

**使用時機**：設計或修改 GitHub Actions workflow、配置 CI/CD、處理 workflow 安全性問題。

**觸發情境**：
- 建立新的 GitHub Actions workflow
- 修復 CI 錯誤或最佳化 pipeline
- 需要 action pinning、OIDC 驗證、權限最小化等安全建議

---

### `Explore` — 程式碼庫探索

**使用時機**：需要快速理解程式碼架構、搜尋特定實作、回答關於程式碼庫的問題。

**觸發情境**：
- 不確定某個功能在哪裡實作
- 需要理解多個檔案之間的關聯
- 進行大範圍的程式碼搜尋

**使用要點**：
- 指定詳細程度：quick（快速概覽）、medium（中等深度）、thorough（深入分析）
- 適合在開始修改前先了解現有程式碼結構
- 可安全地平行呼叫

---

### `AIAgentExpert` — AI Agent 開發

**使用時機**：開發、除錯、評估或部署 AI Agent 應用程式。

**觸發情境**：
- 使用 Microsoft Agent Framework 建立或增強 agent
- 設定 agent tracing、evaluation
- 需要 AI 模型比較與推薦
- 將 agent 部署到 Microsoft Foundry

---

## 外部技能（全域可用）

### `microsoft-foundry` — Foundry 平台管理

**使用時機**：部署、管理、評估 Foundry Agent，或處理平台層級的操作。

**觸發情境**：
- 部署 agent 到 Foundry（Docker build → ACR push → agent create）
- 執行批次評估、prompt 最佳化
- 管理 RBAC、quota、region 設定
- 排查部署失敗、建立 AI Services 資源

---

### `microsoft-foundry-agent-framework-code-gen` — Agent 程式碼產生

**使用時機**：產生、建構、擴充或修復 Microsoft Foundry Agent 的應用程式碼。

**觸發情境**：
- 建立新的 agent 專案骨架
- 為 agent 增加工具（tools）或功能
- 實作多代理工作流程（multi-agent workflow）
- 修復 agent 程式碼錯誤

**注意**：僅處理程式碼層面，部署相關操作應使用 `microsoft-foundry`。

---

### `cosmosdb-best-practices` — Cosmos DB 最佳實踐

**使用時機**：撰寫、審查或重構與 Azure Cosmos DB 互動的程式碼。

**觸發情境**：
- 設計 thread storage 的資料模型與分區鍵
- 實作 CRUD 操作（建立/查詢/更新/刪除執行緒）
- 最佳化查詢效能、RU 消耗
- 處理 429 錯誤的重試邏輯

**本專案重點**：
- Partition key 選用 `user_id`（高基數、符合查詢模式）
- 嵌入式資料模型（訊息嵌入在執行緒文件中）
- 單一項目大小上限 2 MB — 超長對話需考慮分頁策略
- 使用 singleton `CosmosClient` 實例
- 啟用非同步 API 以提升吞吐量

---

### `azure-observability` — Azure 監控

**使用時機**：設定監控、診斷、告警，或查詢日誌。

**觸發情境**：
- 為 Cosmos DB 操作加入 Application Insights 追蹤
- 設定 Log Analytics 查詢或告警規則
- 分析效能瓶頸

---

### `agent-customization` — Copilot 自訂檔案管理

**使用時機**：建立或修改 VS Code 的 `.instructions.md`、`.agent.md`、`SKILL.md` 等自訂檔案。

**觸發情境**：
- 新增或更新 instructions/skills/agents 檔案
- 除錯為何某個 instruction 或 skill 未被觸發
- 配置 `applyTo` 模式或工具限制

---

## 決策樹：如何選擇正確的 Skill 或 Agent

```
使用者需求
├── 功能規劃與設計 → SpecKit 系列（specify → plan → tasks）
├── 程式碼實作 → speckit.implement + 相關技術 skill
│   ├── Agent 程式碼 → microsoft-foundry-agent-framework-code-gen
│   ├── Cosmos DB 操作 → cosmosdb-best-practices
│   └── SDK 使用 → 參考 copilot-sdk-python.instructions.md
├── 部署與平台管理 → microsoft-foundry
├── CI/CD → GitHub Actions Expert
├── Issue 管理 → github-issues（+ speckit.taskstoissues）
├── Git 提交 → git-commit
├── 程式碼庫探索 → Explore agent
├── 監控與診斷 → azure-observability
└── Copilot 設定 → github-copilot-starter / agent-customization
```

## 慣例與注意事項

- **語言**：專案文件與 commit message 使用繁體中文，程式碼中的識別符與註解使用英文
- **規格優先**：任何重大變更應先經過 SpecKit 工作流程（specify → plan → tasks → implement）
- **漸進式實作**：依 tasks.md 中的任務順序逐項完成，每完成一項即 commit
- **安全性**：絕不在程式碼中硬編碼連線字串或密鑰，一律使用環境變數或 Azure Key Vault
- **測試**：每個 CRUD 操作都應有對應的測試案例，涵蓋正常與異常路徑

<!--
同步影響報告
- 版本變更：N/A（範本預留位置） → 1.0.0（初始制定）
- 已修改原則列表：
  - [原則一名稱] → I. 安全優先 (Security-First)
  - [原則二名稱] → II. 型別安全 Python (Type-Safe Python)
  - [原則三名稱] → III. 簡約設計 (Simplicity)
  - [原則四名稱] → IV. 明確錯誤處理 (Explicit Error Handling)
  - [原則五名稱] → V. 環境驅動配置 (Environment-Driven Configuration)
- 新增的區段：
  - 技術約束（取代 [區段二名稱]）
  - 開發工作流程（取代 [區段三名稱]）
- 移除的區段：無
- 需要更新的範本：
  - .specify/templates/plan-template.md — ⚠ 待處理（憲章檢查區段為通用指引，無需修改範本本身）
  - .specify/templates/spec-template.md — ✅ 無需更新（不直接引用憲章原則）
  - .specify/templates/tasks-template.md — ✅ 無需更新（不直接引用憲章原則）
  - specs/001-byo-thread-storage/plan.md — ✅ 已更新（憲章檢查區段已填入具體原則驗證表格）
- 後續待辦事項：無
-->

# BYO Thread Storage 憲章

## 核心原則

### I. 安全優先 (Security-First)

所有認證 MUST 使用 `DefaultAzureCredential`（Azure Identity SDK）；程式碼中
MUST NOT 出現硬編碼的金鑰、連線字串或任何認證資訊。資料隔離 MUST 透過分割
鍵（`user_id`）在儲存層強制實施——跨使用者存取 MUST 統一回傳「查無此執行
緒」以隱藏資源存在性。

**理由**：FR-008、FR-013、SC-005 明確要求；洩漏認證或資源存在性將導致安全
漏洞。

### II. 型別安全 Python (Type-Safe Python)

所有函式簽章 MUST 附加完整型別提示（type hints）。資料結構 MUST 使用
`dataclasses` 或 `Pydantic` 模型定義——MUST NOT 使用原始字典作為核心資料
傳遞。遵循 PEP 8 規範，行寬上限 88 字元（Black 預設），公開 API MUST 附加
Google-style docstrings。

**理由**：型別提示是靜態分析和 IDE 支援的基礎；dataclasses 提供宣告式結構
並減少序列化錯誤。

### III. 簡約設計 (Simplicity)

YAGNI（You Aren't Gonna Need It）——MUST NOT 為假設性的未來需求建立抽象
層。每個模組 SHOULD 不超過 300 行。目錄結構保持扁平化（`src/*.py`），除非
單一模組確實需要拆分為子套件。新增複雜性 MUST 附帶理由。

**理由**：本專案為單一開發者使用的 Python 函式庫，過度工程化會增加維護成本
而非降低。

### IV. 明確錯誤處理 (Explicit Error Handling)

所有 Cosmos DB SDK 例外 MUST 被捕獲並轉換為應用層型別化例外
（`ThreadNotFoundError`、`StorageConnectionError` 等）。MUST NOT 使用空的
`except:` 或靜默吞噬錯誤。對外回傳的錯誤訊息 MUST 可被開發者理解，且
MUST NOT 洩漏內部實作細節。

**理由**：FR-009、SC-004 要求 100% 回傳可理解的錯誤；未處理的 SDK 例外會
使除錯困難且可能洩漏敏感資訊。

### V. 環境驅動配置 (Environment-Driven Configuration)

所有外部連線資訊（端點、資料庫名稱、容器名稱）MUST 透過環境變數傳遞，
並支援 `.env` 檔案載入（`python-dotenv`）。程式碼中 MUST NOT 存在任何寫
死的端點、名稱或路徑。設定類別 MUST 提供 `from_env()` 工廠方法並為選填
欄位定義合理預設值。

**理由**：FR-012 要求；環境變數是跨部署平台（本地、CI、Azure App Service、
Container Apps）最通用的配置機制。

## 技術約束

- **Python 版本**：≥ 3.11（MUST）
- **Azure Cosmos DB SDK**：`azure-cosmos` ≥ 4.7.0（MUST，AAD 認證支援）
- **認證 SDK**：`azure-identity`（MUST，DefaultAzureCredential）
- **Foundry SDK**：`azure-ai-projects`（MUST，AIProjectClient 整合）
- **Cosmos DB 文件上限**：單一文件 ≤ 2 MB（框架限制，約 4,000 條訊息）
- **分割鍵**：`/user_id`（MUST，所有容器操作皆以此為分割鍵路徑）
- **格式化工具**：Black，行寬 88 字元
- **匯入順序**：標準函式庫 → 第三方套件 → 本地模組，各組間空行分隔

## 開發工作流程

- 每個功能 MUST 先完成規格（spec.md）再開始實作。
- 程式碼變更 MUST 在功能分支上進行（`###-feature-name` 格式）。
- 公開 API 變更 MUST 先更新 `contracts/` 中的契約文件。
- 明確處理例外——禁止使用空的 `except:`。
- 使用情境管理器（`with`）處理資源（檔案、連線）。
- 串列推導式優先於 `map()`/`filter()`。

## 治理

本憲章優先於所有其他開發實務。任何與憲章衝突的實作決策 MUST 在 plan.md
的「複雜度追蹤」區段中記錄理由。

修訂程序：
1. 提出修訂需求並說明影響範圍。
2. 更新憲章檔案（`.specify/memory/constitution.md`）。
3. 依語意版本控制遞增版本號（MAJOR：移除/重定義原則；MINOR：新增原則或
   區段；PATCH：措辭澄清或錯字修正）。
4. 更新所有引用憲章原則的產出文件（plan.md 憲章檢查區段）。

合規審查期望：每次 `/speckit.plan` 執行時，MUST 對照本憲章進行原則合規驗
證。

使用 `.github/instructions/python.instructions.md` 作為執行階段的 Python
程式碼風格指引。

**版本**：1.0.0 | **批准日期**：2026-03-22 | **最後修訂**：2026-03-22

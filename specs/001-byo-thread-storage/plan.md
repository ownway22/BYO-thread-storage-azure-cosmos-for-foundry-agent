# 實作計畫：BYO Thread Storage — 以 Azure Cosmos DB 作為 Foundry Agent 的對話執行緒儲存體

**分支**：`001-byo-thread-storage` | **日期**：2026-03-22 | **規格**：`specs/001-byo-thread-storage/spec.md`
**輸入**：來自 `/specs/001-byo-thread-storage/spec.md` 的功能規格

## 摘要

建立自訂 Python 儲存層，將 Azure Cosmos DB for NoSQL 作為 Microsoft Foundry Agent 的對話執行緒儲存體。核心需求涵蓋：

- **CRUD 操作**：建立（FR-001）、讀取（FR-003/FR-004）、追加訊息（FR-002）、刪除（FR-005）、列出使用者執行緒（FR-010）
- **Foundry Agent 整合**：對話迴圈中自動持久化與擷取歷史（FR-006、FR-007）
- **安全與隔離**：`user_id` 分割鍵天然實現資料隔離（FR-013），`DefaultAzureCredential` 認證（FR-008）
- **自動化初始化**：程式碼自動建立資料庫與容器（FR-011），環境變數設定（FR-012）
- **並行控制**：ETag 樂觀並行，衝突時最多重試 3 次（FR-002）
- **統一錯誤處理**：`ThreadNotFoundError` 統一處理不存在與不匹配場景（FR-013），隱藏執行緒存在性

技術方法：自訂 Python 儲存層（非 Foundry Standard Setup BYO），直接以 `azure-cosmos` SDK 操作 Cosmos DB，Messages 嵌入於 Thread 文件中（單次 point read 取得完整對話）。

## 技術情境

**語言/版本**：Python 3.11+  
**主要相依套件**：`azure-cosmos` ≥4.7.0、`azure-identity`、`azure-ai-projects`、`python-dotenv`  
**儲存方式**：Azure Cosmos DB for NoSQL（Serverless 或 ≥400 RU/s）  
**測試工具**：pytest、pytest-asyncio  
**目標平台**：Linux 伺服器（同區域部署於 Azure Cosmos DB）  
**專案類型**：單一專案（Python library + examples）  
**效能目標**：單次 CRUD 操作 < 3 秒（SC-003，同區域部署環境）  
**約束條件**：Cosmos DB 單一文件 ≤ 2 MB（約 4,000 條訊息）、`DefaultAzureCredential` 認證（無硬編碼金鑰）  
**規模/範圍**：單一開發者使用的 Python 函式庫，5 個核心原始碼檔案 + 2 個範例

## 憲章檢查

*關卡：必須在階段 0 研究前通過。階段 1 設計後重新檢查。*

| 原則 | 合規 | 驗證 |
|------|------|------|
| I. 安全優先 | ✅ | FR-008 強制 DefaultAzureCredential；FR-013 以 `user_id` 分割鍵天然隔離，統一回傳 ThreadNotFoundError |
| II. 型別安全 Python | ✅ | data-model.md 使用 dataclasses；contracts/ 所有方法簽章含完整型別提示；Google-style docstrings |
| III. 簡約設計 | ✅ | 5 個 src/ 模組，扁平結構，每個預期 < 300 行；無不必要的抽象層 |
| IV. 明確錯誤處理 | ✅ | exceptions.py 定義 3 個型別化例外（+ 1 個預留）；FR-009 要求轉換 SDK 例外；SC-004 要求 100% 可理解錯誤 |
| V. 環境驅動配置 | ✅ | config.py + from_env()；FR-012 強制環境變數；.env.sample 提供範本 |

- **關卡結果**：✅ 全部通過（無阻擋項目）

## 專案結構

### 文件（此功能）

```text
specs/001-byo-thread-storage/
├── plan.md              # 此檔案（/speckit.plan 指令輸出）
├── research.md          # 階段 0 輸出 — 7 項研究決策
├── data-model.md        # 階段 1 輸出 — Thread/Message 實體定義
├── quickstart.md        # 階段 1 輸出 — 快速開始指南
├── contracts/
│   └── thread_storage_api.md  # 階段 1 輸出 — CosmosThreadStore API 契約
├── checklists/
│   └── requirements.md  # 需求品質檢查（16/16 通過）
└── tasks.md             # 階段 2 輸出 — 22 項任務
```

### 原始碼（儲存庫根目錄）

```text
src/
├── __init__.py          # 匯出公開 API
├── models.py            # Thread、Message dataclass
├── exceptions.py        # ThreadStorageError 例外層級
├── config.py            # ThreadStoreConfig（環境變數載入）
├── thread_store.py      # CosmosThreadStore 核心儲存層
└── agent_integration.py # run_agent_conversation() Foundry 整合

tests/
├── unit/                # 單元測試
├── integration/         # Cosmos DB 整合測試
└── contract/            # API 契約測試

examples/
├── basic_usage.py       # CRUD 操作範例
└── agent_chat.py        # Foundry Agent 多輪對話範例
```

**結構決策**：選用單一專案結構。本功能為純 Python 函式庫（無 Web 框架、無前端），核心為 5 個 `src/` 模組 + 2 個範例。目錄扁平化（`src/*.py` 而非 `src/models/`），因為每個模組預期不超過 300 行（符合 Python 程式碼規範）。

## 複雜度追蹤

> 無憲章違規需說明。

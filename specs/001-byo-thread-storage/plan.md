# 實作計畫：BYO Thread Storage — 以 Azure Cosmos DB 作為 Foundry Agent 的對話執行緒儲存體

**分支**：`001-byo-thread-storage` | **日期**：2026-03-22 | **規格**：`specs/001-byo-thread-storage/spec.md`
**輸入**：來自 `/specs/001-byo-thread-storage/spec.md` 的功能規格

## 摘要

建立一個自訂 Python 儲存層（`CosmosThreadStore`），以 Azure Cosmos DB for NoSQL 作為 Microsoft Foundry Agent 的對話執行緒儲存體。核心能力包含：執行緒 CRUD 操作（FR-001~FR-005）、完整對話歷史擷取（FR-007）、以使用者 ID 列出所有執行緒（FR-010）、Foundry Agent 整合（FR-006）、`user_id` 分割鍵天然資料隔離（FR-013）、以及 DefaultAzureCredential 認證（FR-008）。技術方法：自訂 Python 儲存層搭配 `azure-cosmos` SDK，透過 `AIProjectClient` 與 Foundry Agent 整合。

## 技術情境

**語言/版本**：Python ≥ 3.11  
**主要相依套件**：azure-cosmos ≥ 4.7.0、azure-identity、azure-ai-projects、python-dotenv  
**儲存方式**：Azure Cosmos DB for NoSQL（Serverless 或至少 400 RU/s）  
**測試工具**：手動端到端驗證（T022）；測試目錄已建立供後續自動化  
**目標平台**：Linux/macOS/Windows（Python 函式庫）  
**專案類型**：單一專案（Python 函式庫 + 範例腳本）  
**效能目標**：同區域部署環境下，所有 CRUD 操作 < 3 秒（SC-003）  
**約束條件**：Cosmos DB 單一文件 ≤ 2 MB（約 4,000 條訊息）；單一區域部署  
**規模/範圍**：單一開發者使用的 Python 函式庫；每個使用者預期數十至數百個執行緒

## 憲章檢查

*關卡：必須在階段 0 研究前通過。階段 1 設計後重新檢查。*

| 原則 | 要求 | 設計符合性 | 狀態 |
|------|------|-----------|------|
| I. 安全優先 | MUST DefaultAzureCredential；MUST user_id 隔離 | CosmosThreadStore 建構子預設使用 DefaultAzureCredential（FR-008）；所有方法要求 user_id 參數（FR-013）；不匹配時統一回傳 ThreadNotFoundError | ✅ 通過 |
| II. 型別安全 Python | MUST 完整型別提示；MUST dataclass；MUST NOT 原始字典傳遞 | Thread、Message、ThreadSummary 皆為 dataclass；所有函式簽章含完整型別提示；list_threads 回傳 list[ThreadSummary]（非 dict） | ✅ 通過 |
| III. 簡約設計 | MUST NOT 為假設性需求建抽象；SHOULD 模組 ≤ 300 行；扁平 src/*.py | 6 個模組（models.py、exceptions.py、config.py、thread_store.py、agent_integration.py、__init__.py）；扁平目錄結構；無多餘抽象層 | ✅ 通過 |
| IV. 明確錯誤處理 | MUST 捕獲 Cosmos SDK 例外並轉換；MUST NOT 空 except | CosmosHttpResponseError 按 status_code 轉換為 ThreadNotFoundError / StorageConnectionError；ETag 衝突最多重試 3 次 | ✅ 通過 |
| V. 環境驅動配置 | MUST 環境變數；MUST from_env()；MUST NOT 寫死端點 | ThreadStoreConfig.from_env() 載入所有設定；.env.sample 提供範本；預設值僅用於選填欄位 | ✅ 通過 |

**關卡結果**：5/5 通過，無違規。可進入階段 0。

## 專案結構

### 文件（此功能）

```text
specs/001-byo-thread-storage/
├── plan.md              # 此檔案（/speckit.plan 指令輸出）
├── research.md          # 階段 0 輸出 — 7 項研究決策
├── data-model.md        # 階段 1 輸出 — Thread、Message、ThreadSummary 實體定義
├── quickstart.md        # 階段 1 輸出 — 快速開始指南
├── contracts/
│   └── thread_storage_api.md  # 階段 1 輸出 — CosmosThreadStore API 契約
└── tasks.md             # 階段 2 輸出 — 22 個任務（T001~T022）
```

### 原始碼（儲存庫根目錄）

```text
src/
├── __init__.py          # 公開 API 匯出
├── models.py            # Thread、Message、ThreadSummary dataclass
├── exceptions.py        # ThreadStorageError 階層
├── config.py            # ThreadStoreConfig dataclass + from_env()
├── thread_store.py      # CosmosThreadStore 核心類別
└── agent_integration.py # run_agent_conversation() Foundry 整合

examples/
├── basic_usage.py       # CRUD 操作示範
└── agent_chat.py        # 多輪 Agent 對話示範

tests/
├── unit/
├── integration/
└── contract/

.env.sample              # 環境變數範本
requirements.txt         # 相依套件
pyproject.toml          # 專案設定
```

**結構決策**：採用扁平 `src/*.py` 結構（憲章原則 III），6 個模組各自負責單一關注點。不使用子套件，因為模組數量少且關係簡單。

## 複雜度追蹤

> 無違規。所有設計決策皆符合憲章 5 項原則，無需額外說明理由。

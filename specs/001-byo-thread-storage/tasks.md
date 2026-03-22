# 任務：BYO Thread Storage — 以 Azure Cosmos DB 作為 Foundry Agent 的對話執行緒儲存體

**輸入**：來自 `/specs/001-byo-thread-storage/` 的設計文件
**先決條件**：plan.md、spec.md、research.md、data-model.md、contracts/thread_storage_api.md、quickstart.md

**測試**：規格中的 9 個驗收情境（US1×2、US2×3、US3×2、US4×2）作為端到端驗證的測試目標，由 T022 在端到端驗證階段逐一手動執行與確認。若後續需要自動化測試，可在 tests/integration/ 目錄中新增對應的測試任務。

**組織方式**：任務依使用者故事分組，以便每個故事可獨立實作與測試。

## 格式：`[ID] [P?] [Story] 描述`

- **[P]**：可平行執行（不同檔案、無相依性）
- **[Story]**：此任務所屬的使用者故事（例如 US1、US2、US3、US4）
- 描述中包含確切的檔案路徑

---

## 階段 1：設置（專案初始化）

**目的**：建立專案目錄結構與基礎配置檔案

- [x] T001 根據 plan.md 建立專案目錄結構：src/、tests/unit/、tests/integration/、tests/contract/、examples/，以及所有必要的 __init__.py 檔案
- [x] T002 [P] 建立 pyproject.toml，設定專案名稱 byo-thread-storage、Python ≥3.11、相依套件（azure-cosmos≥4.7.0、azure-identity、azure-ai-projects、python-dotenv）、Black 88 字元行寬
- [x] T003 [P] 建立 requirements.txt，包含 azure-cosmos>=4.7.0、azure-identity、azure-ai-projects、python-dotenv
- [x] T004 [P] 建立 .env.sample，包含 COSMOS_ENDPOINT（必填）、COSMOS_DATABASE_NAME=thread_storage、COSMOS_CONTAINER_NAME=threads、AZURE_AI_PROJECT_ENDPOINT 各項環境變數說明

---

## 階段 2：基礎建設（阻擋性先決條件）

**目的**：建立所有使用者故事共用的核心模組——資料模型、例外、設定、儲存層初始化

**⚠️ 重要**：此階段完成前不可開始任何使用者故事工作

- [x] T005 [P] 依據 data-model.md 在 src/models.py 建立 Thread、Message 與 ThreadSummary dataclass，包含所有欄位（Thread：id、user_id、messages、created_at、updated_at、metadata；ThreadSummary：id、user_id、created_at、updated_at、metadata）、預設值工廠、以及 Thread 的 to_dict()/from_dict() 序列化方法
- [x] T006 [P] 依據 contracts/thread_storage_api.md 在 src/exceptions.py 建立四個自訂例外類別：ThreadStorageError（基礎類別）、ThreadNotFoundError、AccessDeniedError（預留供未來 RBAC 擴充，目前不會被觸發）、StorageConnectionError（FR-009）
- [x] T007 [P] 依據 contracts/thread_storage_api.md 在 src/config.py 建立 ThreadStoreConfig dataclass，包含 cosmos_endpoint（必填）、cosmos_database_name（預設 thread_storage）、cosmos_container_name（預設 threads）、azure_ai_project_endpoint（選填），以及 from_env() classmethod 透過 python-dotenv 載入環境變數（FR-012）
- [x] T008 依據 contracts/thread_storage_api.md 在 src/thread_store.py 實作 CosmosThreadStore 類別的 __init__() 建構子（以 DefaultAzureCredential 建立 CosmosClient，FR-008）與 initialize() 方法（自動建立資料庫與容器，分割鍵 /user_id，FR-011），並在連線失敗時拋出 StorageConnectionError

**檢查點**：基礎建設就緒——CosmosThreadStore 可初始化並連線至 Cosmos DB，現在可以開始使用者故事實作

---

## 階段 3：使用者故事 1 — 建立並持久化新對話執行緒（優先順序：P1）🎯 最小可行產品 (MVP)

**目標**：當使用者與 Agent 開啟新對話時，系統在 Cosmos DB 中建立一筆新的執行緒紀錄，包含唯一識別碼、使用者識別碼、建立時間與空的訊息列表

**獨立測試**：觸發一次 create_thread 呼叫，至 Cosmos DB 中驗證確實產生了一筆含正確結構（id、user_id、messages=[]、created_at、updated_at、metadata）的執行緒文件

### 使用者故事 1 的實作

- [x] T009 [US1] 在 src/thread_store.py 實作 create_thread(user_id, metadata) 方法：建立 Thread 物件、以 to_dict() 序列化後寫入 Cosmos DB 容器、回傳 Thread 物件（FR-001）
- [x] T010 [US1] 建立 examples/basic_usage.py，示範初始化 CosmosThreadStore、呼叫 create_thread 建立新執行緒、印出執行緒 ID 與結構（參考 quickstart.md 第 3 節）

**檢查點**：使用者故事 1 完成——可建立並持久化新對話執行緒至 Cosmos DB

---

## 階段 4：使用者故事 2 — 追加訊息並保留完整對話歷史（優先順序：P1）

**目標**：每次使用者發送訊息或 Agent 回覆時，訊息被即時追加至 Cosmos DB 對應執行緒；Agent 互動前取回完整對話歷史作為上下文

**獨立測試**：在已建立的執行緒中連續發送多條訊息，驗證每條訊息皆被追加至 Cosmos DB 的 messages 陣列，且 get_messages 回傳完整歷史（按時間排序）；透過 agent_chat.py 驗證 Agent 能基於歷史回應

### 使用者故事 2 的實作

- [x] T011 [US2] 在 src/thread_store.py 實作 append_message(thread_id, user_id, role, content) 方法：先驗證 role 必須是 "system"、"user"、"assistant" 之一（否則拋出 ValueError），再以 point read 取得執行緒文件（user_id 分割鍵天然隔離，FR-013），以 Read → Modify → Replace（ETag 樂觀並行，衝突時最多重試 3 次）將新 Message 追加至 messages 陣列尾端並更新 updated_at，回傳新建的 Message 物件（FR-002）
- [x] T012 [US2] 在 src/thread_store.py 實作 get_messages(thread_id, user_id) 方法：以 point read 取得執行緒文件、驗證歸屬權（FR-013），回傳完整訊息列表（不做截斷，FR-004、FR-007）
- [x] T013 [US2] 在 src/agent_integration.py 實作 run_agent_conversation(store, user_id, user_message, thread_id=None, agent_id=None) 函式：若 thread_id 為 None 則呼叫 create_thread 建立新執行緒，呼叫 append_message 持久化使用者訊息，以 get_messages 取回完整歷史，透過 AIProjectClient 將歷史送至 Foundry Agent 模型取得回覆（若 agent_id 為 None 則使用預設 Agent），再呼叫 append_message 持久化 Agent 回覆，回傳 (reply, thread_id)（FR-006、FR-007）
- [x] T014 [US2] 建立 examples/agent_chat.py，示範多輪對話流程：初始化 store、第一輪建立新執行緒、第二輪延續同一執行緒、印出每輪的 Agent 回覆以驗證上下文保留（參考 quickstart.md 第 4 節）

**檢查點**：使用者故事 2 完成——可追加訊息、取回完整歷史，並與 Foundry Agent 進行多輪上下文對話

---

## 階段 5：使用者故事 3 — 查詢與擷取指定執行緒（優先順序：P2）

**目標**：開發者可以執行緒 ID 查詢完整執行緒資料（含所有訊息與中繼資料），以及以使用者 ID 列出該使用者的所有執行緒摘要

**獨立測試**：建立一個含已知訊息的執行緒，以 get_thread 驗證回傳資料完整且結構正確；建立多個執行緒後以 list_threads 驗證回傳正確的摘要清單；查詢不存在的執行緒驗證回傳 ThreadNotFoundError

### 使用者故事 3 的實作

- [x] T015 [US3] 在 src/thread_store.py 實作 get_thread(thread_id, user_id) 方法：以 point read（id + partition key）取得完整 Thread 文件，以 from_dict() 反序列化為 Thread 物件回傳；若文件不存在則拋出 ThreadNotFoundError（FR-003、FR-013）
- [x] T016 [US3] 在 src/thread_store.py 實作 list_threads(user_id) 方法：以 user_id 為分割鍵執行查詢，僅回傳摘要欄位（id、user_id、created_at、updated_at、metadata），回傳 list[ThreadSummary]（FR-010、憲章原則 II）
- [x] T017 [US3] 更新 examples/basic_usage.py，新增 get_thread 與 list_threads 的使用範例，展示查詢單一執行緒與列出使用者所有執行緒

**檢查點**：使用者故事 3 完成——可查詢特定執行緒完整資料，以及列出使用者的所有歷史對話清單

---

## 階段 6：使用者故事 4 — 刪除指定執行緒（優先順序：P3）

**目標**：開發者可以執行緒 ID 從 Cosmos DB 永久刪除一個執行緒及其所有訊息，以滿足資料保留規範

**獨立測試**：建立一個執行緒、對其執行 delete_thread、再以 get_thread 確認回傳 ThreadNotFoundError

### 使用者故事 4 的實作

- [x] T018 [US4] 在 src/thread_store.py 實作 delete_thread(thread_id, user_id) 方法：以 partition key（user_id）+ id（thread_id）執行 delete_item，若不存在則拋出 ThreadNotFoundError（FR-005、FR-013）
- [x] T019 [US4] 更新 examples/basic_usage.py，新增 delete_thread 的使用範例與刪除後查詢驗證

**檢查點**：使用者故事 4 完成——可永久刪除指定執行緒，刪除後查詢確認已不存在

---

## 階段 7：收尾與跨切面關注點

**目的**：文件撰寫、完整性驗證、quickstart 端到端驗證

- [x] T020 [P] 建立 README.md，包含專案概述、前提條件、安裝步驟、環境變數設定、基本使用範例、Foundry Agent 整合說明，以及檔案結構說明
- [x] T021 程式碼清理：確認所有模組的 import 正確、src/__init__.py 匯出公開 API（CosmosThreadStore、Thread、Message、ThreadSummary、ThreadStoreConfig、例外類別）、遵循 PEP 8 與 Black 88 字元格式
- [ ] T022 依據 quickstart.md 執行端到端驗證：安裝相依、設定環境變數、執行 basic_usage.py 與 agent_chat.py，確認所有 13 項功能需求（FR-001 ~ FR-013）與 5 項成功標準（SC-001 ~ SC-005）皆已滿足。同時逐一驗證 spec.md 中 4 個使用者故事的 9 個驗收情境（US1×2、US2×3、US3×2、US4×2）。其中 SC-001 驗證方式：確認從安裝依賴到成功建立第一個執行緒不超過 5 個操作步驟；SC-003 驗證方式：以 Python `time` 模組計時各 CRUD 操作，確認單次操作在同區域環境下不超過 3 秒

---

## 相依性與執行順序

### 階段相依性

- **設置（階段 1）**：無相依性——可立即開始
- **基礎建設（階段 2）**：相依於設置完成——阻擋所有使用者故事
- **使用者故事 1（階段 3）**：相依於基礎建設完成
- **使用者故事 2（階段 4）**：相依於使用者故事 1 完成（需要 create_thread 已實作）
- **使用者故事 3（階段 5）**：相依於基礎建設完成（可與 US1/US2 平行，但建議在 US1 後以便測試）
- **使用者故事 4（階段 6）**：相依於基礎建設完成（可與 US1/US2/US3 平行，但建議在 US1 後以便測試）
- **收尾（階段 7）**：相依於所有使用者故事完成

### 使用者故事相依性

- **使用者故事 1（P1）**：可在基礎建設後立即開始——不相依於其他故事
- **使用者故事 2（P1）**：相依於 US1（append_message 需要已建立的執行緒；agent_integration 使用 create_thread）
- **使用者故事 3（P2）**：邏輯上獨立於 US1/US2（get_thread/list_threads 是獨立操作），但建議在 US1 後實作以便有資料可查詢
- **使用者故事 4（P3）**：邏輯上獨立，但建議在 US1 後實作以便有資料可刪除

### 每個使用者故事內部

- 同一檔案的方法按順序實作（避免編輯衝突）
- 範例檔案在核心方法實作後建立/更新
- 故事完成後再移至下一個優先順序

### 平行執行機會

- **階段 1**：T002、T003、T004 可平行執行（不同檔案）
- **階段 2**：T005、T006、T007 可平行執行（不同檔案），T008 需等待三者完成
- **跨故事**：基礎建設完成後，US3 和 US4 理論上可與 US1/US2 平行（但單人開發建議循序）
- **階段 7**：T020 可與 T021 平行

---

## 平行執行範例：基礎建設階段

```
# 同時啟動三個獨立模組的建立：
Task T005: "在 src/models.py 建立 Thread 與 Message dataclass"
Task T006: "在 src/exceptions.py 建立四個自訂例外類別"
Task T007: "在 src/config.py 建立 ThreadStoreConfig"

# 三者完成後，啟動儲存層初始化：
Task T008: "在 src/thread_store.py 實作 CosmosThreadStore 建構子與 initialize()"
```

## 平行執行範例：使用者故事 3

```
# US3 可在基礎建設完成後與 US1/US2 平行開始（若有多人）
# 但更建議在 US1 後循序進行：

Task T015: "實作 get_thread() — 可在 US1(T009) 完成後開始"
Task T016: "實作 list_threads() — 需在 T015 後（同檔案）"
Task T017: "更新 basic_usage.py — 需在 T015, T016 後"
```

---

## 實作策略

### 最小可行產品 (MVP) 優先（使用者故事 1）

1. 完成階段 1：設置
2. 完成階段 2：基礎建設（重要——阻擋所有故事）
3. 完成階段 3：使用者故事 1（建立執行緒）
4. **停止並驗證**：執行 basic_usage.py，確認 Cosmos DB 中出現正確結構的執行緒文件
5. 準備就緒則繼續下一個故事

### 漸進式交付

1. 完成設置 + 基礎建設 → 基礎就緒（CosmosThreadStore 可初始化）
2. 新增使用者故事 1 → 驗證 → 可建立執行緒（最小可行產品！）
3. 新增使用者故事 2 → 驗證 → 可進行多輪 Agent 對話（核心價值！）
4. 新增使用者故事 3 → 驗證 → 可查詢歷史對話
5. 新增使用者故事 4 → 驗證 → 可刪除對話（合規性）
6. 收尾 → 文件完善、端到端驗證
7. 每個故事增加價值而不破壞先前的故事

### 需求追蹤矩陣

| 需求 | 對應任務 | 階段 |
|------|---------|------|
| FR-001 建立執行緒 | T009 | 階段 3 (US1) |
| FR-002 追加訊息 | T011 | 階段 4 (US2) |
| FR-003 擷取執行緒 | T015 | 階段 5 (US3) |
| FR-004 擷取訊息列表 | T012 | 階段 4 (US2) |
| FR-005 刪除執行緒 | T018 | 階段 6 (US4) |
| FR-006 Foundry Agent 整合 | T013 | 階段 4 (US2) |
| FR-007 完整歷史回傳 | T012, T013 | 階段 4 (US2) |
| FR-008 Azure 身分驗證 | T008 | 階段 2 |
| FR-009 錯誤提示 | T006, T008~T018 | 階段 2~6 |
| FR-010 列出使用者執行緒 | T016 | 階段 5 (US3) |
| FR-011 自動建立 DB/容器 | T008 | 階段 2 |
| FR-012 環境變數設定 | T004, T007 | 階段 1, 2 |
| FR-013 使用者資料隔離 | T011, T012, T015, T018 | 階段 4~6 |

---

## 備註

- 所有方法實作時需匯入並使用 src/exceptions.py 中的自訂例外，捕獲 CosmosHttpResponseError 並轉換為應用層例外（research.md 研究 7）
- Cosmos DB 操作使用 point read（id + partition key）以獲得最佳效能
- append_message 使用 ETag 樂觀並行控制（contracts/thread_storage_api.md）
- 所有時間戳記使用 UTC ISO 8601 格式（data-model.md）
- 每個任務或邏輯群組完成後提交 git
- 在任何檢查點停止以獨立驗證故事

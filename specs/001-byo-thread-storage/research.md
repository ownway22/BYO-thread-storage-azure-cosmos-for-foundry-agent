# 研究報告：BYO Thread Storage

**功能分支**：`001-byo-thread-storage`  
**日期**：2026-03-22  
**狀態**：完成

## 研究摘要

本報告整合了 7 篇官方參考文獻的研究發現，解決了實作計畫中的所有「需要釐清」項目。

---

## 研究 1：BYO Thread Storage 架構模式

### 決策：採用自訂 Python 儲存層（非純基礎設施設定）

**理由**：

Foundry Agent Service 的 Standard Setup 提供基礎設施層級的 BYO Thread Storage，自動在 Cosmos DB 中建立 `enterprise_memory` 資料庫，包含三個容器：
- `thread-message-store`：終端使用者對話訊息
- `system-thread-message-store`：內部系統訊息
- `agent-entity-store`：Agent 中繼資料（指令、工具、名稱）

然而，本專案的需求（FR-010 列出使用者執行緒、FR-013 儲存層強制隔離）超出了內建 BYO 的能力範圍。因此，我們將建立一個**自訂 Python 儲存層**，直接操作 Cosmos DB，在 Foundry Agent 互動流程中負責對話的持久化與擷取。

**考慮的替代方案**：
- 純 Standard Setup BYO：由 Foundry 服務自動管理 Cosmos DB，但不支援自訂分割鍵或 user_id 查詢
- 混合方案：同時使用 Standard Setup BYO + 自訂層 → 過於複雜，資料重複

---

## 研究 2：Cosmos DB 分割鍵策略

### 決策：使用 `user_id` 作為分割鍵

**理由**：

根據規格書在釐清階段的決定，需同時支援：
1. 以 `user_id` 列出某使用者的所有執行緒（FR-010）
2. 以 `thread_id` + `user_id` 讀寫單一執行緒

使用 `user_id` 作為分割鍵：
- 列出使用者執行緒時為**單一分割區查詢**（最高效）
- 讀寫個別執行緒需同時提供 `user_id` + `thread_id`（`id` 欄位），仍為單一分割區的 point read
- 滿足 FR-013 資料隔離需求（所有操作都自然包含 `user_id`）

**Cosmos DB 最佳實務對齊**：
- 高基數（每個使用者一個分割區）✓
- 支援最常見查詢模式 ✓
- 避免熱點分割區（假設使用者數量夠多）✓

**考慮的替代方案**：
- `thread_id` 作為分割鍵：列出使用者執行緒時需跨分割區查詢（效能差、成本高）
- 階層式分割鍵 `(user_id, thread_id)`：Cosmos DB for NoSQL 支援 HPK，但對本需求規模而言過於複雜

---

## 研究 3：Azure SDK 與認證最佳實務

### 決策：使用 `azure-identity` + `DefaultAzureCredential`

**理由**：

根據官方文件與 Travel Agent 範例：
- 使用 `DefaultAzureCredential` 統一本地開發（Azure CLI）與生產環境（Managed Identity）
- Cosmos DB 連線使用 `CosmosClient` + `aad_credentials` 參數
- 避免硬編碼金鑰或連線字串（FR-008、SC-005）

**所需 SDK 套件**：
- `azure-cosmos`：Cosmos DB 操作（≥4.7.0，支援 AAD 認證）
- `azure-identity`：Azure 身分驗證
- `azure-ai-projects`：Foundry AIProjectClient 整合
- `python-dotenv`：環境變數載入（FR-012）

**考慮的替代方案**：
- 主金鑰（Master Key）認證：簡單但違反 FR-008
- 連線字串認證：Foundry SDK 已棄用連線字串方式

---

## 研究 4：Foundry Agent 整合模式

### 決策：透過 `AIProjectClient` 建立 Agent，自訂儲存層處理對話迴圈

**理由**：

根據 Travel Agent 範例與 Foundry 文件：
- 使用 `AIProjectClient` 建立和管理 Agent
- Agent 的對話迴圈中，在發送訊息至模型前，從自訂儲存層取回歷史
- 模型回覆後，將新訊息持久化至儲存層
- 這種模式讓我們完全控制對話歷史的格式與儲存位置

**整合流程**：
```
使用者訊息 → 從 Cosmos DB 取回歷史 → 組裝上下文 → 發送至 Agent 模型
                                                          ↓
                                                     Agent 回覆
                                                          ↓
                                              將回覆持久化至 Cosmos DB
```

**考慮的替代方案**：
- 使用 Foundry 內建的 thread/message API（如 `agents.create_thread`）：但資料存在微軟管理的儲存中，非 BYO
- 使用 Standard Setup 的內建 BYO：基礎設施層級，不支援自訂邏輯

---

## 研究 5：容器初始化策略

### 決策：程式碼層級自動建立（`create_database_if_not_exists` + `create_container_if_not_exists`）

**理由**：

根據 FR-011，開發者只需提供端點、資料庫名稱和容器名稱。Cosmos DB Python SDK 提供：
- `client.create_database_if_not_exists(id=db_name)`
- `database.create_container_if_not_exists(id=container_name, partition_key=PartitionKey(path="/user_id"))`

吞吐量設定：依 Cosmos DB 文件建議，使用 Server less 或至少 400 RU/s（單一容器用途，非 Foundry Standard Setup 的 3000 RU/s 需求）。

**考慮的替代方案**：
- Bicep/ARM 範本預先建立：增加部署複雜度
- 手動建立：違反 FR-011 的自動化需求

---

## 研究 6：資料隔離實作方式

### 決策：所有操作以 `user_id` 為必要參數，儲存層驗證歸屬權

**理由**：

根據 FR-013 的釐清結果：
- 所有 API 方法簽章都必須包含 `user_id` 參數
- `get_thread`：使用 `user_id`（分割鍵）+ `thread_id`（id）做 point read，若讀不到即為「不存在或不屬於該使用者」
- `list_threads`：以 `user_id` 查詢，天然隔離
- `delete_thread`：先驗證歸屬權（point read），再刪除
- `append_message`：先驗證歸屬權，再追加

Cosmos DB 的分割鍵設計天然支援這種隔離 — 以 `user_id` 作為分割鍵，跨使用者查詢在應用層被阻止。

**考慮的替代方案**：
- 行級安全性（Cosmos DB RBAC）：Cosmos DB NoSQL 不支援行級 RBAC
- 分離容器（每個使用者一個容器）：管理成本和複雜度過高

---

## 研究 7：錯誤處理模式

### 決策：捕獲 `CosmosHttpResponseError` 並轉換為應用層例外

**理由**：

根據 FR-009 和 Cosmos DB SDK 最佳實務：
- 捕獲 `CosmosHttpResponseError`，根據 `status_code` 分類處理
- 404（NotFound）→ `ThreadNotFoundError`（包含 FR-013 歸屬權不匹配——分割鍵設計下 point read 以 `(thread_id, user_id)` 查詢，`user_id` 不匹配時天然回傳 404，統一為「查無此執行緒」，隱藏執行緒存在性）
- 409（Conflict / ETag 衝突）→ 自動重試最多 3 次（FR-002），若仍失敗則拋出錯誤
- 429（TooManyRequests）→ SDK 內建重試，透明處理
- 連線逾時 → `StorageConnectionError`
- `AccessDeniedError` 類別保留但標註為未來 RBAC 擴充預留，目前不會被觸發

**考慮的替代方案**：
- 直接透傳 SDK 例外：違反 FR-009 的「清楚錯誤提示」要求
- 通用例外包裝：缺乏足夠的錯誤分類資訊
- 顯式區分「不存在」與「無權限」：洩漏執行緒存在性，安全性較差

# 資料模型：BYO Thread Storage

**功能分支**：`001-byo-thread-storage`  
**日期**：2026-03-22  
**來源**：`specs/001-byo-thread-storage/spec.md`

---

## 實體定義

### 1. Thread（對話執行緒）

代表一段完整的使用者-Agent 對話上下文。

| 欄位 | 型別 | 必要 | 說明 |
|------|------|------|------|
| `id` | `str` | ✅ | 唯一識別碼（UUID v4），Cosmos DB 文件 ID |
| `user_id` | `str` | ✅ | 所屬使用者識別碼，**分割鍵**（Partition Key） |
| `messages` | `list[Message]` | ✅ | 對話訊息列表（按時間戳記排序） |
| `created_at` | `str` (ISO 8601) | ✅ | 建立時間（UTC） |
| `updated_at` | `str` (ISO 8601) | ✅ | 最後修改時間（UTC） |
| `metadata` | `dict[str, Any]` | ❌ | 選用中繼資料（例如 agent_id、標題等） |

**Cosmos DB 文件結構**：

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user-abc-123",
  "messages": [
    {
      "role": "user",
      "content": "你好，我想規劃一趟旅行。",
      "timestamp": "2026-03-22T10:15:30Z"
    },
    {
      "role": "assistant",
      "content": "您好！很高興為您服務。請問您想去哪裡旅行呢？",
      "timestamp": "2026-03-22T10:15:35Z"
    }
  ],
  "created_at": "2026-03-22T10:15:30Z",
  "updated_at": "2026-03-22T10:15:35Z",
  "metadata": {
    "agent_id": "agent-travel-001",
    "title": "旅行規劃"
  }
}
```

### 2. Message（訊息）

代表執行緒中的一條對話訊息。作為嵌入文件存在於 Thread 的 `messages` 陣列中。

| 欄位 | 型別 | 必要 | 說明 |
|------|------|------|------|
| `role` | `str` | ✅ | 訊息角色：`"system"` / `"user"` / `"assistant"` |
| `content` | `str` | ✅ | 訊息文字內容 |
| `timestamp` | `str` (ISO 8601) | ✅ | 訊息產生時間（UTC） |

### 3. ThreadSummary（執行緒摘要）

代表 `list_threads` 回傳的輕量執行緒摘要，不含訊息列表以減少傳輸量（FR-010、憲章原則 II）。

| 欄位 | 型別 | 必要 | 說明 |
|------|------|------|------|
| `id` | `str` | ✅ | 執行緒識別碼 |
| `user_id` | `str` | ✅ | 所屬使用者識別碼 |
| `created_at` | `str` (ISO 8601) | ✅ | 建立時間（UTC） |
| `updated_at` | `str` (ISO 8601) | ✅ | 最後修改時間（UTC） |
| `metadata` | `dict[str, Any]` | ❌ | 選用中繼資料 |

---

## 關係

```
Thread (1) ──contains──▶ (N) Message
```

- **Thread → Message**：一對多嵌入（embedding）關係
- Message **沒有獨立的 Cosmos DB 文件**，而是嵌入在 Thread 文件的 `messages` 陣列中
- 這是因為 Message 的存取模式永遠是「連同 Thread 一起讀取全部」（FR-007）

---

## 嵌入 vs. 參考決策

| 考量 | 嵌入（選定） | 參考（排除） |
|------|-------------|-------------|
| 存取模式 | 總是讀取整個對話歷史 | 需獨立查詢個別訊息 |
| 寫入模式 | 追加訊息時更新整個文件 | 每個訊息獨立文件 |
| Cosmos DB 限制 | 單一文件 ≤ 2 MB | 無文件大小問題 |
| 效能 | 單次讀取取得完整對話 | 需多次查詢 |
| 複雜度 | 簡單 | 需維護外鍵關係 |

**選擇嵌入的理由**：FR-007 明確要求「從儲存體取回完整對話歷史」，且每次 Agent 互動都需要全部訊息作為上下文。嵌入模式以單次 point read 即可取得完整資料，是最高效的方式。

**2 MB 限制風險**：假設每條訊息平均 500 bytes（含 JSON 開銷），一個 Thread 可容納約 4,000 條訊息。對於絕大多數對話場景已足夠。邊界情境（EC-003：超過 1,000 條訊息）在此限制內。

---

## 驗證規則

### Thread

- `id`：非空字串，UUID v4 格式
- `user_id`：非空字串，最大長度 256 字元
- `messages`：可為空列表（新建執行緒時）
- `created_at` / `updated_at`：有效 ISO 8601 日期時間字串
- `metadata`：若提供，必須為字典；值可為字串、數字或布林

### Message

- `role`：必須為 `"system"`、`"user"` 或 `"assistant"` 之一
- `content`：非空字串
- `timestamp`：有效 ISO 8601 日期時間字串

---

## 狀態轉換

Thread 的生命週期：

```
[不存在] ──create_thread──▶ [已建立]
                               │
                    append_message ◁──┘
                               │
                         ┌─────┘
                         ▼
                    [已更新]（updated_at 更新）
                         │
              ┌──────────┤
              ▼          ▼
    append_message   delete_thread
              │          │
              ▼          ▼
         [已更新]    [已刪除/不存在]
```

- **建立**：產生新文件，`messages` 為空列表，`created_at` = `updated_at` = 當前時間
- **追加訊息**：將 Message 追加至 `messages` 陣列尾端，更新 `updated_at`
- **刪除**：從 Cosmos DB 永久移除文件

---

## Cosmos DB 容器設定

| 設定 | 值 |
|------|-----|
| 資料庫名稱 | 透過環境變數 `COSMOS_DATABASE_NAME` 設定（預設 `thread_storage`） |
| 容器名稱 | 透過環境變數 `COSMOS_CONTAINER_NAME` 設定（預設 `threads`） |
| 分割鍵路徑 | `/user_id` |
| 索引策略 | 預設（自動索引所有屬性） |
| 吞吐量 | Serverless 或至少 400 RU/s |

---

## Python 資料類別

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class Message:
    """對話訊息。"""

    role: str  # "system" | "user" | "assistant"
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class Thread:
    """對話執行緒。"""

    user_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    messages: list[Message] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThreadSummary:
    """執行緒摘要（list_threads 回傳用，不含訊息列表）。"""

    id: str
    user_id: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)
```

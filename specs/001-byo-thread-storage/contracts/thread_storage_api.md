# API 契約：CosmosThreadStore

**功能分支**：`001-byo-thread-storage`  
**日期**：2026-03-22  
**來源**：`specs/001-byo-thread-storage/spec.md` 功能性需求 FR-001 ~ FR-013

---

## 概述

`CosmosThreadStore` 是核心儲存層類別，封裝所有 Cosmos DB 操作。所有公開方法都要求 `user_id` 參數以強制使用者資料隔離（FR-013）。

---

## 類別：`CosmosThreadStore`

### 建構與初始化

```python
class CosmosThreadStore:
    def __init__(
        self,
        endpoint: str,
        database_name: str,
        container_name: str,
        credential: TokenCredential | None = None,
    ) -> None:
        """初始化 CosmosThreadStore。

        Args:
            endpoint: Cosmos DB 帳號端點 URL。
            database_name: 資料庫名稱。
            container_name: 容器名稱。
            credential: Azure TokenCredential 實例。
                若未提供，使用 DefaultAzureCredential。
        """

    def initialize(self) -> None:
        """初始化資料庫與容器（FR-011）。

        若資料庫或容器不存在，自動建立。
        分割鍵設定為 /user_id。

        Raises:
            StorageConnectionError: 無法連線至 Cosmos DB。
        """
```

---

### 方法契約

#### 1. `create_thread` — 建立執行緒（FR-001）

```python
def create_thread(
    self,
    user_id: str,
    metadata: dict[str, Any] | None = None,
) -> Thread:
    """在 Cosmos DB 中建立新的對話執行緒。

    Args:
        user_id: 使用者識別碼。
        metadata: 選用中繼資料。

    Returns:
        新建立的 Thread 物件（含自動產生的 id、時間戳記）。

    Raises:
        StorageConnectionError: Cosmos DB 連線失敗。
    """
```

| 項目 | 值 |
|------|-----|
| 對應需求 | FR-001 |
| 輸入 | `user_id: str`, `metadata: dict | None` |
| 輸出 | `Thread` |
| 副作用 | 在 Cosmos DB 建立新文件 |
| 冪等 | 否（每次呼叫建立新 Thread） |

---

#### 2. `get_thread` — 擷取執行緒（FR-003）

```python
def get_thread(
    self,
    thread_id: str,
    user_id: str,
) -> Thread:
    """以 thread_id 和 user_id 擷取完整執行緒資料。

    Args:
        thread_id: 執行緒識別碼。
        user_id: 使用者識別碼（分割鍵，同時用於驗證歸屬權）。

    Returns:
        完整的 Thread 物件，包含所有訊息與中繼資料。

    Raises:
        ThreadNotFoundError: 執行緒不存在或不屬於該使用者。
        StorageConnectionError: Cosmos DB 連線失敗。
    """
```

| 項目 | 值 |
|------|-----|
| 對應需求 | FR-003, FR-013 |
| 輸入 | `thread_id: str`, `user_id: str` |
| 輸出 | `Thread` |
| 副作用 | 無 |
| Cosmos DB 操作 | Point read（`id` + partition key） |

---

#### 3. `get_messages` — 擷取訊息列表（FR-004）

```python
def get_messages(
    self,
    thread_id: str,
    user_id: str,
) -> list[Message]:
    """以 thread_id 擷取該執行緒的訊息列表。

    Args:
        thread_id: 執行緒識別碼。
        user_id: 使用者識別碼。

    Returns:
        訊息列表（按時間戳記排序）。

    Raises:
        ThreadNotFoundError: 執行緒不存在或不屬於該使用者。
        StorageConnectionError: Cosmos DB 連線失敗。
    """
```

| 項目 | 值 |
|------|-----|
| 對應需求 | FR-004, FR-007, FR-013 |
| 輸入 | `thread_id: str`, `user_id: str` |
| 輸出 | `list[Message]` |
| 副作用 | 無 |
| 備註 | 回傳全量訊息，不做截斷（FR-007） |

---

#### 4. `append_message` — 追加訊息（FR-002）

```python
def append_message(
    self,
    thread_id: str,
    user_id: str,
    role: str,
    content: str,
) -> Message:
    """將一條訊息追加到指定執行緒。

    Args:
        thread_id: 執行緒識別碼。
        user_id: 使用者識別碼。
        role: 訊息角色（"system" / "user" / "assistant"）。
        content: 訊息文字內容。

    Returns:
        新追加的 Message 物件。

    Raises:
        ValueError: role 不是 "system"、"user"、"assistant" 之一。
        ThreadNotFoundError: 執行緒不存在或不屬於該使用者。
        StorageConnectionError: Cosmos DB 連線失敗。
| 輸入 | `thread_id: str`, `user_id: str`, `role: str`, `content: str` |
| 輸出 | `Message` |
| 副作用 | 更新 Cosmos DB 文件（追加訊息、更新 `updated_at`） |
| Cosmos DB 操作 | Read → Modify → Replace（樂觀並行，使用 ETag；衝突時最多重試 3 次） |

---

#### 5. `delete_thread` — 刪除執行緒（FR-005）

```python
def delete_thread(
    self,
    thread_id: str,
    user_id: str,
) -> None:
    """從 Cosmos DB 中刪除指定執行緒。

    Args:
        thread_id: 執行緒識別碼。
        user_id: 使用者識別碼。

    Returns:
        None

    Raises:
        ThreadNotFoundError: 執行緒不存在或不屬於該使用者。
        StorageConnectionError: Cosmos DB 連線失敗。
    """
```

| 項目 | 值 |
|------|-----|
| 對應需求 | FR-005, FR-013 |
| 輸入 | `thread_id: str`, `user_id: str` |
| 輸出 | `None` |
| 副作用 | 從 Cosmos DB 永久刪除文件 |
| Cosmos DB 操作 | Delete item（`id` + partition key） |

---

#### 6. `list_threads` — 列出使用者執行緒（FR-010）

```python
def list_threads(
    self,
    user_id: str,
) -> list[ThreadSummary]:
    """列出指定使用者的所有對話執行緒摘要。

    Args:
        user_id: 使用者識別碼。

    Returns:
        ThreadSummary 物件列表，每個摘要包含：
        - id: 執行緒識別碼
        - user_id: 使用者識別碼
        - created_at: 建立時間
        - updated_at: 最後更新時間
        - metadata: 中繼資料

    Raises:
        StorageConnectionError: Cosmos DB 連線失敗。
    """
```

| 項目 | 值 |
|------|-----|
| 對應需求 | FR-010 |
| 輸入 | `user_id: str` |
| 輸出 | `list[ThreadSummary]` |
| 副作用 | 無 |
| Cosmos DB 操作 | 分割區內查詢（SELECT id, user_id, created_at, updated_at, metadata FROM c WHERE c.user_id = @user_id） |
| 備註 | 不含 `messages`，以減少傳輸量；回傳型別化 dataclass 而非原始字典（憲章原則 II） |

---

## 例外類別

```python
class ThreadStorageError(Exception):
    """儲存層基底例外。"""

class ThreadNotFoundError(ThreadStorageError):
    """執行緒不存在。對應 Cosmos DB 404。"""

class AccessDeniedError(ThreadStorageError):
    """使用者無權存取此資源。預留供未來 RBAC 擴充使用，目前不會被觸發。"""

class StorageConnectionError(ThreadStorageError):
    """Cosmos DB 連線失敗或逾時。"""
```

---

## 設定介面

```python
@dataclass
class ThreadStoreConfig:
    """儲存層設定（FR-012）。"""

    cosmos_endpoint: str          # COSMOS_ENDPOINT
    cosmos_database_name: str     # COSMOS_DATABASE_NAME（預設 "thread_storage"）
    cosmos_container_name: str    # COSMOS_CONTAINER_NAME（預設 "threads"）
    azure_ai_project_endpoint: str | None = None  # AZURE_AI_PROJECT_ENDPOINT（選填，整合 Agent 時需要）

    @classmethod
    def from_env(cls) -> "ThreadStoreConfig":
        """從環境變數載入設定。

        Required env vars:
            COSMOS_ENDPOINT: Cosmos DB 帳號端點。

        Optional env vars:
            COSMOS_DATABASE_NAME: 資料庫名稱（預設 "thread_storage"）。
            COSMOS_CONTAINER_NAME: 容器名稱（預設 "threads"）。
            AZURE_AI_PROJECT_ENDPOINT: Foundry 專案端點（整合 Agent 時需要）。

        Raises:
            ValueError: 必要的環境變數未設定。
        """
```

---

## 環境變數對照

| 環境變數 | 必要 | 說明 | 預設值 |
|----------|------|------|--------|
| `COSMOS_ENDPOINT` | ✅ | Cosmos DB 帳號端點 URL | — |
| `COSMOS_DATABASE_NAME` | ❌ | 資料庫名稱 | `thread_storage` |
| `COSMOS_CONTAINER_NAME` | ❌ | 容器名稱 | `threads` |
| `AZURE_AI_PROJECT_ENDPOINT` | ✅* | Foundry 專案端點（整合 Agent 時需要） | — |

*僅在使用 `agent_integration.py` 時需要。

---

## 整合介面（FR-006）

```python
def run_agent_conversation(
    store: CosmosThreadStore,
    user_id: str,
    user_message: str,
    thread_id: str | None = None,
    agent_id: str | None = None,
) -> tuple[str, str]:
    """與 Foundry Agent 進行一輪對話，自動持久化至儲存層。

    Args:
        store: CosmosThreadStore 實例。
        user_id: 使用者識別碼。
        user_message: 使用者訊息文字。
        thread_id: 現有執行緒 ID。若為 None，建立新執行緒。
        agent_id: Foundry Agent ID。若為 None，使用預設 Agent。

    Returns:
        (agent_reply, thread_id) 元組：Agent 回覆文字與執行緒 ID。

    Raises:
        ThreadNotFoundError, StorageConnectionError
    """
```

**整合流程**：
1. 若 `thread_id` 為 None → `store.create_thread(user_id)` → 取得新 `thread_id`
2. `store.append_message(thread_id, user_id, "user", user_message)` → 追加使用者訊息
3. `store.get_messages(thread_id, user_id)` → 取回完整歷史
4. 組裝 messages 上下文 → 傳送至 Foundry Agent 模型
5. 取得 Agent 回覆 → `store.append_message(thread_id, user_id, "assistant", reply)`
6. 回傳 `(reply, thread_id)`

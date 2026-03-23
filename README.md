# BYO Thread Storage — Azure Cosmos DB for Foundry Agent

用 Azure Cosmos DB 儲存 Microsoft Foundry Agent 的對話紀錄，讓你完全掌控對話歷史的查詢、審計與刪除。

---

## 專案簡介

Microsoft Foundry Agent 預設在內部管理對話歷史。本專案實作 **Bring Your Own (BYO) Thread Storage**，透過 **OpenAI Responses API endpoint** 與 Agent 互動，並將對話執行緒（thread）與訊息（message）持久化到你自己的 Azure Cosmos DB，好處包括：

- 自由查詢、匯出對話紀錄
- 按需刪除執行緒（合規需求）
- 將對話歷史整合進你的應用邏輯

---

## 專案結構

```
├── src/
│   ├── models.py              # 資料模型：Thread、Message dataclass
│   ├── thread_store.py        # 核心：CosmosThreadStore（所有 Cosmos DB CRUD）
│   ├── agent_integration.py   # Foundry Agent 整合（對話流程串接）
│   ├── config.py              # 環境變數設定
│   └── exceptions.py          # 自定義例外
├── examples/
│   ├── basic_usage.py         # CRUD 操作範例
│   ├── agent_chat.py          # 多輪 Agent 對話範例（腳本式）
│   └── interactive_chat.py    # 互動式 Agent 對話（推薦）
├── tests/                     # 單元測試 & 整合測試
├── pyproject.toml
└── requirements.txt
```

---

## 快速開始

### 前置需求

| 需求 | 說明 |
|------|------|
| Microsoft Foundry agent | Agent 對話需要 |
| Azure Cosmos DB for NoSQL | Serverless 或 ≥ 400 RU/s |
| Cosmos DB RBAC | 你的 Azure 身份需要帳戶上的 **Cosmos DB Built-in Data Contributor** 角色 |
| Cosmos DB 網路存取 | 帳戶的 **Networking** 需啟用 **Public network access**，或將開發機 IP 加入防火牆白名單 |
| Azure CLI | `az login` 完成，或設定 Managed Identity |
| Clone Repo | `git clone https://github.com/ownway22/BYO-thread-storage-azure-cosmos-for-foundry-agent.git` |
| Python | ≥ 3.11 |
| [uv](https://docs.astral.sh/uv/) | Python 套件管理器 |

### 1. 安裝相依套件

```bash
uv sync
```

### 2. 設定環境變數

複製 `.env.sample` 為 `.env`，填入你的值：

```bash
cp .env.sample .env
```

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `COSMOS_ENDPOINT` | — | Cosmos DB endpoint URL |
| `COSMOS_DATABASE_NAME` | `thread_storage` | 資料庫名稱 |
| `COSMOS_CONTAINER_NAME` | `threads` | Container 名稱 |
| `AZURE_AI_PROJECT_ENDPOINT` | — | Foundry project endpoint |
| `FOUNDRY_AGENT_NAME` | — | Foundry Agent 應用名稱（如 `RAI-agent`） |
| `FOUNDRY_MODEL_NAME` | — | Agent 底層模型（如 `gpt-4.1-mini`） |

### 3. 執行範例

**互動式 Agent 對話**：

```bash
uv run examples/interactive_chat.py
```

啟動後會進入互動式對話模式，你可以即時與 Foundry Agent 進行多輪對話。以下是執行成功的範例畫面：

![互動式 Agent 對話範例](images/chat-with-foundry-agent.png)

結束對話後，所有訊息會一次儲存到 Cosmos DB，並在 terminal 顯示 **Thread ID**（如上圖中的 `adbf6bb7-fbd7-4b26-b9d3-112fb7a8217b`）。

也可以透過 console script 啟動：

```bash
uv run interactive-chat
```

### 4. 驗證對話紀錄

執行完成後，你可以到 **Azure Portal** 的 Cosmos DB 帳戶，開啟 **Data Explorer**，在 `threads` container 中以 Thread ID `adbf6bb7-fbd7-4b26-b9d3-112fb7a8217b` 查詢，即可看到完整的對話紀錄已成功寫入：

![Cosmos DB Data Explorer 中的對話紀錄](images/thread-storage-in-cosmos-db.png)

這證明對話歷史已透過 `CosmosThreadStore` 正確持久化到你自己的 Azure Cosmos DB。你也可以使用 VS Code 的 [Azure Cosmos DB 擴充套件](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-cosmosdb) 進行查詢。

### 5. 架構概覽

```mermaid
flowchart TB
    subgraph chat [對話階段]
        A["Your App<br/>(interactive_chat.py)"] -->|"① 使用者輸入<br/>② 帶完整歷史呼叫 Responses API"| B["Foundry Agent"]
        B -->|"③ 回傳 Agent 回覆"| A
    end

    subgraph save [儲存階段 — 對話結束時]
        A -->|"④ 建立 thread<br/>⑤ 批次寫入訊息"| C["CosmosThreadStore"]
        C -->|"azure-cosmos SDK"| D[("Azure Cosmos DB<br/>NoSQL")]
    end

    subgraph cosmosdb [Cosmos DB 細節]
        D --- E["threads container<br/>partition key: /user_id"]
        E --- F["Thread document<br/>id, user_id, messages ..."]
    end

    subgraph foundry [Foundry 細節]
        B --- G["project_endpoint<br/>/applications/agent<br/>/protocols/openai"]
    end
```

---

## Agent × Cosmos DB 整合關鍵

### 資料模型（`src/models.py`）

採用 **嵌入式設計**——訊息直接嵌入在 Thread 文件中，以 `user_id` 做為 partition key：

```python
@dataclass
class Thread:
    user_id: str                    # partition key（高基數）
    id: str                         # thread UUID
    messages: list[Message]         # 嵌入的訊息陣列
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

@dataclass
class Message:
    role: str       # "user" | "assistant" | "system"
    content: str
    timestamp: str
```

`Thread.to_dict()` / `Thread.from_dict()` 負責與 Cosmos DB 文件格式互轉。

### Cosmos DB CRUD（`src/thread_store.py`）

`CosmosThreadStore` 封裝所有資料庫操作：

| 方法 | 作用 |
|------|------|
| `initialize()` | 建立 database / container（若不存在） |
| `create_thread()` | 建立新對話執行緒 → `container.create_item()` |
| `append_message()` | **寫入訊息的核心方法**——讀取 thread → 追加 message → `replace_item()` + ETag 樂觀並行控制（最多重試 3 次） |
| `get_messages()` | 取得某 thread 的完整訊息列表 |
| `get_thread()` | 以 point read 取得單一 thread |
| `list_threads()` | 參數化查詢列出使用者所有 thread（不含 messages，節省 RU） |
| `delete_thread()` | 刪除指定 thread |

**`append_message()` 是最關鍵的方法**，使用 ETag 樂觀並行確保多 client 同時寫入時資料不會遺失。

### 對話流程串接（`src/agent_integration.py`）

`run_agent_conversation()` 把 Cosmos DB 和 Foundry Agent 串在一起：

```
1. thread_id 為空 → store.create_thread()        # 建立新執行緒
2. store.append_message("user", user_message)      # 存入使用者訊息
3. store.get_messages()                             # 取出完整歷史
4. Responses API → Foundry Agent endpoint          # 帶歷史上下文送給 Agent
5. store.append_message("assistant", agent_reply)   # 存入 Agent 回覆
```

Agent 端點格式為 `{project_endpoint}/applications/{agent_name}/protocols/openai`，使用 `openai.OpenAI` 客戶端的 `responses.create()` 方法呼叫。這確保**每一輪對話的使用者訊息和 Agent 回覆都被持久化**，下次對話時可取回完整歷史做為上下文。

---

## 參考資料

- [BYO Thread Storage in Azure AI Foundry Using Python — Tech Community](https://techcommunity.microsoft.com/discussions/azure-ai-foundry-discussions/byo-thread-storage-in-azure-ai-foundry-using-python/4468147)
- [Azure AI Foundry Connection for Azure Cosmos DB and BYO Thread Storage — DevBlogs](https://devblogs.microsoft.com/cosmosdb/azure-ai-foundry-connection-for-azure-cosmos-db-and-byo-thread-storage-in-azure-ai-agent-service/)
- [Azure Cosmos DB for Azure Agent Service — Microsoft Learn](https://learn.microsoft.com/en-us/azure/cosmos-db/gen-ai/azure-agent-service)

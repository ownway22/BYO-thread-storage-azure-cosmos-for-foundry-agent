# 快速開始：BYO Thread Storage

**功能分支**：`001-byo-thread-storage`  
**日期**：2026-03-22

---

## 前提條件

1. **Python 3.11+** 已安裝
2. **Azure Cosmos DB for NoSQL 帳號**（Serverless 或至少 400 RU/s）
3. **Azure AI Foundry 專案**，已部署至少一個 Agent 模型（例如 gpt-4o）
4. **Azure CLI 已登入**（`az login`）或環境有 Managed Identity

---

## 1. 安裝相依套件

```bash
pip install -r requirements.txt
```

`requirements.txt` 內容：
```
azure-cosmos>=4.7.0
azure-identity
azure-ai-projects
python-dotenv
```

---

## 2. 設定環境變數

複製 `.env.sample` 為 `.env` 並填入您的值：

```bash
cp .env.sample .env
```

```env
# 必要
COSMOS_ENDPOINT=https://your-cosmosdb-account.documents.azure.com:443/

# 選填（有預設值）
COSMOS_DATABASE_NAME=thread_storage
COSMOS_CONTAINER_NAME=threads

# Foundry Agent 整合（使用 agent_integration 時需要）
AZURE_AI_PROJECT_ENDPOINT=https://your-foundry-project.api.azureml.ms
```

---

## 3. 基本使用

```python
from dotenv import load_dotenv
from src.config import ThreadStoreConfig
from src.thread_store import CosmosThreadStore

load_dotenv()

# 初始化（自動建立資料庫與容器）
config = ThreadStoreConfig.from_env()
store = CosmosThreadStore(
    endpoint=config.cosmos_endpoint,
    database_name=config.cosmos_database_name,
    container_name=config.cosmos_container_name,
)
store.initialize()

# 建立執行緒
thread = store.create_thread(user_id="user-001")
print(f"建立執行緒：{thread.id}")

# 追加訊息
store.append_message(thread.id, "user-001", "user", "你好！")
store.append_message(thread.id, "user-001", "assistant", "您好，有什麼可以幫您的嗎？")

# 讀取完整歷史
messages = store.get_messages(thread.id, "user-001")
for msg in messages:
    print(f"[{msg.role}] {msg.content}")

# 列出使用者所有執行緒
threads = store.list_threads("user-001")
for t in threads:
    print(f"Thread {t.id} — 最後更新：{t.updated_at}")

# 刪除執行緒
store.delete_thread(thread.id, "user-001")
```

---

## 4. 與 Foundry Agent 整合

```python
from dotenv import load_dotenv
from src.config import ThreadStoreConfig
from src.thread_store import CosmosThreadStore
from src.agent_integration import run_agent_conversation

load_dotenv()

config = ThreadStoreConfig.from_env()
store = CosmosThreadStore(
    endpoint=config.cosmos_endpoint,
    database_name=config.cosmos_database_name,
    container_name=config.cosmos_container_name,
)
store.initialize()

# 第一輪對話（自動建立新執行緒）
reply, thread_id = run_agent_conversation(
    store=store,
    user_id="user-001",
    user_message="我想規劃一趟去日本的旅行",
)
print(f"Agent：{reply}")
print(f"Thread ID：{thread_id}")

# 第二輪對話（延續同一執行緒）
reply, _ = run_agent_conversation(
    store=store,
    user_id="user-001",
    user_message="我偏好去京都，有什麼建議嗎？",
    thread_id=thread_id,
)
print(f"Agent：{reply}")
```

---

## 5. 驗證成功標準

| 標準 | 驗證方式 |
|------|----------|
| SC-001：5 分鐘內完成設定 | 上述步驟 1-3 可在 5 分鐘內完成 |
| SC-002：多輪對話引用上下文 | 步驟 4 中第二輪對話 Agent 應引用「日本」 |
| SC-003：CRUD < 3 秒 | 所有操作應在 3 秒内回應 |
| SC-004：錯誤訊息可理解 | 嘗試存取不存在的 thread_id 應得到 `ThreadNotFoundError` |
| SC-005：無硬編碼金鑰 | 所有認證透過 `DefaultAzureCredential` |

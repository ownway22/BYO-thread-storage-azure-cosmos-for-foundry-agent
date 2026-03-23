"""多輪 Foundry Agent 對話範例 — 透過 Cosmos DB 保留對話上下文。

示範如何將每輪對話的訊息持久化到 Azure Cosmos DB，
讓 Agent 在後續回合能記住先前的對話內容。

前置準備：
  1. 複製 .env.sample 為 .env，填入 COSMOS_ENDPOINT、
     AZURE_AI_PROJECT_ENDPOINT、FOUNDRY_AGENT_NAME、FOUNDRY_MODEL_NAME。
  2. 確認你的 Azure 身份具有 Cosmos DB 與 AI Foundry 的存取權限。
  3. 執行 uv sync 安裝相依套件。
"""

from dotenv import load_dotenv

from src.agent_integration import run_agent_conversation
from src.config import ThreadStoreConfig
from src.thread_store import CosmosThreadStore


def main() -> None:
    """執行兩輪 Agent 對話，並將歷史紀錄存入 Cosmos DB。"""
    load_dotenv()

    # ------------------------------------------------------------------
    # 步驟 1：初始化 Cosmos DB 儲存層
    # ------------------------------------------------------------------
    config = ThreadStoreConfig.from_env()
    store = CosmosThreadStore(
        endpoint=config.cosmos_endpoint,
        database_name=config.cosmos_database_name,
        container_name=config.cosmos_container_name,
    )
    store.initialize()
    print("✓ Storage initialised")

    user_id = "example-user-001"

    # ------------------------------------------------------------------
    # 步驟 2：第一輪對話（thread_id=None → 自動建立新執行緒）
    # ------------------------------------------------------------------
    user_msg_1 = "I want to plan a trip to Japan."
    print(f"\n[User] {user_msg_1}")

    reply_1, thread_id = run_agent_conversation(
        store=store,
        user_id=user_id,
        user_message=user_msg_1,
        agent_name=config.foundry_agent_name,
        model_name=config.foundry_model_name,
    )
    print(f"[Agent] {reply_1}")
    print(f"\n  Thread ID: {thread_id}")

    # ------------------------------------------------------------------
    # 步驟 3：第二輪對話（帶入同一個 thread_id，Agent 應能回憶上一輪內容）
    # ------------------------------------------------------------------
    user_msg_2 = "I prefer Kyoto. Any recommendations?"
    print(f"\n[User] {user_msg_2}")

    reply_2, _ = run_agent_conversation(
        store=store,
        user_id=user_id,
        user_message=user_msg_2,
        thread_id=thread_id,
        agent_name=config.foundry_agent_name,
        model_name=config.foundry_model_name,
    )
    print(f"[Agent] {reply_2}")

    # ------------------------------------------------------------------
    # 步驟 4：驗證對話紀錄已持久化到 Cosmos DB
    # ------------------------------------------------------------------
    messages = store.get_messages(thread_id, user_id)
    print(f"\n✓ Conversation persisted — {len(messages)} messages in Cosmos DB:")
    for msg in messages:
        print(f"  [{msg.role:9s}] {msg.content[:80]}")

    # 清理（選用）— 預設註解掉以保留 Cosmos DB 中的紀錄
    # store.delete_thread(thread_id, user_id)
    # print(f"\n✓ Thread {thread_id} cleaned up")


if __name__ == "__main__":
    main()

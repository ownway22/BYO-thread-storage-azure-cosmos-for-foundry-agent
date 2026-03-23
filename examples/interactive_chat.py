"""互動式 Foundry Agent 聊天 — 對話結束後自動儲存到 Cosmos DB。

執行後進入即時對話模式，所有訊息暫存於記憶體中。
使用者輸入 exit / quit 或按 Ctrl+C 結束對話時，
程式會一次性將完整對話寫入 Cosmos DB，並顯示 Thread ID 供後續查詢。

使用方式：
    uv run examples/interactive_chat.py

前置準備：
    1. 複製 .env.sample 為 .env，填入 COSMOS_ENDPOINT、
       AZURE_AI_PROJECT_ENDPOINT、FOUNDRY_AGENT_NAME、FOUNDRY_MODEL_NAME。
    2. 確認你的 Azure 身份具有 Cosmos DB 與 AI Foundry 的存取權限。
    3. 執行 uv sync 安裝相依套件。
"""

import signal
import sys

import openai
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from src.config import ThreadStoreConfig
from src.thread_store import CosmosThreadStore

_AZURE_ML_SCOPE = "https://ml.azure.com/.default"


def main() -> None:
    """啟動互動式 Foundry Agent 聊天。"""
    load_dotenv()
    config = ThreadStoreConfig.from_env()

    # 步驟 1：檢查必要的環境變數是否已設定
    for attr, env_var in [
        ("azure_ai_project_endpoint", "AZURE_AI_PROJECT_ENDPOINT"),
        ("foundry_agent_name", "FOUNDRY_AGENT_NAME"),
        ("foundry_model_name", "FOUNDRY_MODEL_NAME"),
    ]:
        if not getattr(config, attr):
            sys.exit(f"Error: {env_var} environment variable is required.")

    # 步驟 2：初始化 Cosmos DB 連線（提前驗證設定是否正確）
    store = CosmosThreadStore(
        endpoint=config.cosmos_endpoint,
        database_name=config.cosmos_database_name,
        container_name=config.cosmos_container_name,
    )
    store.initialize()
    print("✓ Cosmos DB connection ready")

    # 步驟 3：建立 OpenAI 客戶端，指向 Foundry Agent 端點
    credential = DefaultAzureCredential()
    token = credential.get_token(_AZURE_ML_SCOPE).token
    base_url = (
        f"{config.azure_ai_project_endpoint.rstrip('/')}"
        f"/applications/{config.foundry_agent_name}/protocols/openai"
    )
    openai_client = openai.OpenAI(
        base_url=base_url,
        api_key=token,
        default_query={"api-version": "2025-11-15-preview"},
    )

    user_id = (
        input("Enter your user ID (default: interactive-user): ").strip()
        or "interactive-user"
    )

    messages: list[tuple[str, str]] = []  # 暫存對話：(角色, 內容)
    saved = False  # 防止重複儲存

    # ------------------------------------------------------------------
    # 輔助函式：將對話儲存到 Cosmos DB 並印出 Thread ID
    # ------------------------------------------------------------------
    def _save_and_report() -> None:
        nonlocal saved
        if saved:
            return
        saved = True

        if not messages:
            print("\nNo messages to save.")
            return

        thread = store.create_thread(
            user_id=user_id,
            metadata={"source": "interactive_chat"},
        )
        for role, content in messages:
            store.append_message(thread.id, user_id, role, content)

        print(f"\n{'=' * 55}")
        print("  ✓ Conversation saved to Cosmos DB")
        print(f"{'=' * 55}")
        print(f"  Thread ID : {thread.id}")
        print(f"  Messages  : {len(messages)}")
        print(f"  User ID   : {user_id}")
        print(f"{'=' * 55}")

    # ------------------------------------------------------------------
    # 攔截 Ctrl+C，確保對話在中斷時也能儲存
    # ------------------------------------------------------------------
    def _handle_sigint(_sig: int, _frame: object) -> None:
        print()  # ^C 後換行
        _save_and_report()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_sigint)

    # ------------------------------------------------------------------
    # 步驟 4：進入互動式對話迴圈
    # ------------------------------------------------------------------
    print(f"\n{'=' * 55}")
    print("  Interactive Foundry Agent Chat")
    print(f"{'=' * 55}")
    print("  Type your message and press Enter.")
    print("  Type 'exit' or 'quit' or press Ctrl+C to end.")
    print(f"{'=' * 55}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except EOFError:
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        messages.append(("user", user_input))

        try:
            payload = [{"role": r, "content": c} for r, c in messages]
            response = openai_client.responses.create(
                model=config.foundry_model_name,
                input=payload,
            )
            reply = response.output_text
            messages.append(("assistant", reply))
            print(f"\nAgent: {reply}\n")
        except Exception as exc:
            print(f"\nError communicating with agent: {exc}\n")
            messages.pop()  # 移除送出失敗的使用者訊息

    _save_and_report()


if __name__ == "__main__":
    main()

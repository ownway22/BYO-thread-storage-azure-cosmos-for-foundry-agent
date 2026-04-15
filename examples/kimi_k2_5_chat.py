"""互動式 Kimi-K2.5 聊天 — 每輪對話即時持久化到 Cosmos DB。

串接 Microsoft Foundry 上的 Kimi-K2.5 模型，透過 Chat Completions API
進行多輪互動，並在每一輪對話結束時立即將使用者訊息與模型回覆
寫入 Azure Cosmos DB，保證對話紀錄不會因中斷而遺失。

使用方式：
    uv run examples/kimi_k2_5_chat.py

前置準備：
    1. 複製 .env.sample 為 .env，填入 COSMOS_ENDPOINT 與
       AZURE_OPENAI_ENDPOINT。
    2. 設定 FOUNDRY_MODEL_NAME=Kimi-K2.5（或你的部署名稱）。
    3. 確認你的 Azure 身份具有 Cosmos DB 與 Azure OpenAI 的存取權限。
    4. 執行 uv sync 安裝相依套件。
"""

import os
import sys
import time

import openai
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

from src.config import ThreadStoreConfig
from src.thread_store import CosmosThreadStore

_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"
_DEFAULT_MODEL = "Kimi-K2.5"


def _build_openai_client(endpoint: str) -> openai.OpenAI:
    """Build an OpenAI client targeting the Azure OpenAI endpoint via Entra ID."""
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), _COGNITIVE_SCOPE
    )
    return openai.OpenAI(base_url=endpoint, api_key=token_provider())


def main() -> None:
    """啟動互動式 Kimi-K2.5 聊天，每輪即時寫入 Cosmos DB。"""
    load_dotenv()
    config = ThreadStoreConfig.from_env()

    # ------------------------------------------------------------------
    # 步驟 1：驗證環境變數
    # ------------------------------------------------------------------
    azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if not azure_openai_endpoint:
        sys.exit(
            "Error: AZURE_OPENAI_ENDPOINT environment variable is required.\n"
            "Example: https://<resource>.openai.azure.com/openai/v1/"
        )

    model_name = config.foundry_model_name or _DEFAULT_MODEL

    # ------------------------------------------------------------------
    # 步驟 2：初始化 Cosmos DB 儲存層
    # ------------------------------------------------------------------
    store = CosmosThreadStore(
        endpoint=config.cosmos_endpoint,
        database_name=config.cosmos_database_name,
        container_name=config.cosmos_container_name,
    )
    store.initialize()
    print("✓ Cosmos DB connection ready")

    # ------------------------------------------------------------------
    # 步驟 3：建立 OpenAI 客戶端（指向 Azure OpenAI 端點）
    # ------------------------------------------------------------------
    openai_client = _build_openai_client(azure_openai_endpoint)
    print(f"✓ Azure OpenAI client ready (model: {model_name})")

    # ------------------------------------------------------------------
    # 步驟 4：取得使用者 ID 與選擇性恢復既有執行緒
    # ------------------------------------------------------------------
    user_id = (
        input("Enter your user ID (default: interactive-user): ").strip()
        or "interactive-user"
    )
    existing_thread_id = input(
        "Resume thread ID (leave blank for new conversation): "
    ).strip() or None

    if existing_thread_id:
        try:
            messages = store.get_messages(existing_thread_id, user_id)
            print(f"\n✓ Resumed thread {existing_thread_id} "
                  f"({len(messages)} previous messages)")
            for msg in messages:
                label = "You" if msg.role == "user" else "Kimi-K2.5"
                print(f"  [{label}] {msg.content[:120]}")
        except Exception as exc:
            print(f"⚠ Could not resume thread: {exc}")
            print("  Starting a new conversation instead.\n")
            existing_thread_id = None

    if existing_thread_id:
        thread_id: str | None = existing_thread_id
    else:
        thread = store.create_thread(user_id=user_id)
        thread_id = thread.id

    # ------------------------------------------------------------------
    # 步驟 5：互動式對話迴圈
    # ------------------------------------------------------------------
    print(f"\n{'=' * 55}")
    print(f"  Kimi-K2.5 Interactive Chat")
    print(f"{'=' * 55}")
    print(f"  Thread ID : {thread_id}")
    print(f"  User ID   : {user_id}")
    print(f"  Model     : {model_name}")
    print(f"{'=' * 55}")
    print("  Type your message and press Enter.")
    print("  Type 'exit' or 'quit' or press Ctrl+C to end.")
    print(f"{'=' * 55}\n")

    turn_count = 0

    try:
        while True:
            try:
                user_input = input("You: ").strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                break

            # --- 持久化使用者訊息 ---
            store.append_message(thread_id, user_id, "user", user_input)

            # --- 從 Cosmos DB 讀取完整歷史送給模型 ---
            history = store.get_messages(thread_id, user_id)
            payload = [
                {"role": m.role, "content": m.content}
                for m in history
                if m.role in ("user", "assistant")
            ]

            try:
                # 429 重試（最多 3 次，指數退避）
                last_err = None
                for attempt in range(3):
                    try:
                        response = openai_client.chat.completions.create(
                            model=model_name,
                            messages=payload,
                        )
                        last_err = None
                        break
                    except openai.RateLimitError as e:
                        last_err = e
                        wait = 2 ** attempt * 5
                        print(f"\n⚠ Rate limited, retrying in {wait}s…")
                        time.sleep(wait)

                if last_err is not None:
                    raise last_err

                reply = response.choices[0].message.content or ""

                # --- 持久化模型回覆 ---
                store.append_message(thread_id, user_id, "assistant", reply)
                turn_count += 1
                print(f"\nKimi-K2.5: {reply}\n")

            except openai.AuthenticationError:
                print("\n⚠ Token expired, refreshing credential…")
                openai_client = _build_openai_client(azure_openai_endpoint)
                print("  Credential refreshed. Please resend your message.\n")
                # 回滾已寫入但未得到回覆的使用者訊息不影響一致性，
                # 下次重送時會自然追加
            except Exception as exc:
                print(f"\n⚠ Error communicating with model: {exc}\n")

    except KeyboardInterrupt:
        print()  # ^C 後換行

    # ------------------------------------------------------------------
    # 步驟 6：對話結束，顯示摘要
    # ------------------------------------------------------------------
    if thread_id and turn_count > 0:
        total = len(store.get_messages(thread_id, user_id))
        print(f"\n{'=' * 55}")
        print("  ✓ All messages persisted to Cosmos DB")
        print(f"{'=' * 55}")
        print(f"  Thread ID : {thread_id}")
        print(f"  Messages  : {total}")
        print(f"  User ID   : {user_id}")
        print(f"  Model     : {model_name}")
        print(f"{'=' * 55}")
    elif turn_count == 0:
        print("\nNo messages exchanged.")


if __name__ == "__main__":
    main()

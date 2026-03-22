"""Multi-turn Foundry Agent conversation example using BYO Thread Storage.

Demonstrates how conversation context is preserved across multiple turns
by persisting messages in Azure Cosmos DB (US2, FR-006, FR-007).

Prerequisites:
  1. Copy .env.sample to .env and set COSMOS_ENDPOINT and
     AZURE_AI_PROJECT_ENDPOINT.
  2. Ensure your Azure identity has the required roles on both Cosmos DB
     and Azure AI Foundry.
  3. Run: pip install -r requirements.txt
"""

from dotenv import load_dotenv

from src.agent_integration import run_agent_conversation
from src.config import ThreadStoreConfig
from src.thread_store import CosmosThreadStore


def main() -> None:
    """Run a two-turn agent conversation with persisted history."""
    load_dotenv()

    # ------------------------------------------------------------------
    # Initialise storage
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
    # Turn 1: Start a new conversation (thread_id=None → creates thread)
    # ------------------------------------------------------------------
    user_msg_1 = "I want to plan a trip to Japan."
    print(f"\n[User] {user_msg_1}")

    reply_1, thread_id = run_agent_conversation(
        store=store,
        user_id=user_id,
        user_message=user_msg_1,
    )
    print(f"[Agent] {reply_1}")
    print(f"\n  Thread ID: {thread_id}")

    # ------------------------------------------------------------------
    # Turn 2: Continue the same conversation (agent should recall Japan)
    # ------------------------------------------------------------------
    user_msg_2 = "I prefer Kyoto. Any recommendations?"
    print(f"\n[User] {user_msg_2}")

    reply_2, _ = run_agent_conversation(
        store=store,
        user_id=user_id,
        user_message=user_msg_2,
        thread_id=thread_id,
    )
    print(f"[Agent] {reply_2}")

    # ------------------------------------------------------------------
    # Verify history is persisted
    # ------------------------------------------------------------------
    messages = store.get_messages(thread_id, user_id)
    print(f"\n✓ Conversation persisted — {len(messages)} messages in Cosmos DB:")
    for msg in messages:
        print(f"  [{msg.role:9s}] {msg.content[:80]}")

    # Cleanup (optional)
    store.delete_thread(thread_id, user_id)
    print(f"\n✓ Thread {thread_id} cleaned up")


if __name__ == "__main__":
    main()

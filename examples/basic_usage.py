"""Basic usage examples for BYO Thread Storage.

Demonstrates all CRUD operations against Azure Cosmos DB:
  - create_thread
  - append_message
  - get_messages
  - get_thread
  - list_threads
  - delete_thread

Prerequisites:
  1. Copy .env.sample to .env and set COSMOS_ENDPOINT.
  2. Ensure your Azure identity has Cosmos DB Data Contributor role.
  3. Run: pip install -r requirements.txt
"""

from dotenv import load_dotenv

from src.config import ThreadStoreConfig
from src.exceptions import ThreadNotFoundError
from src.thread_store import CosmosThreadStore


def main() -> None:
    """Run CRUD operation examples against Cosmos DB."""
    load_dotenv()

    # ------------------------------------------------------------------
    # Initialise storage (auto-creates DB and container if absent)
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
    # US1: Create a thread
    # ------------------------------------------------------------------
    thread = store.create_thread(
        user_id=user_id,
        metadata={"title": "Basic usage example"},
    )
    print(f"\n✓ Thread created: {thread.id}")
    print(f"  user_id   : {thread.user_id}")
    print(f"  created_at: {thread.created_at}")
    print(f"  messages  : {thread.messages}")
    print(f"  metadata  : {thread.metadata}")

    # ------------------------------------------------------------------
    # US2: Append messages
    # ------------------------------------------------------------------
    store.append_message(thread.id, user_id, "user", "Hello!")
    store.append_message(
        thread.id, user_id, "assistant", "Hi! How can I help you today?"
    )
    store.append_message(thread.id, user_id, "user", "What is 2 + 2?")
    store.append_message(thread.id, user_id, "assistant", "2 + 2 = 4.")
    print(f"\n✓ 4 messages appended to thread {thread.id}")

    # Read back messages
    messages = store.get_messages(thread.id, user_id)
    print(f"\n✓ Retrieved {len(messages)} messages:")
    for msg in messages:
        print(f"  [{msg.role:9s}] {msg.content}")

    # ------------------------------------------------------------------
    # US3: Get a specific thread and list all threads
    # ------------------------------------------------------------------
    fetched = store.get_thread(thread.id, user_id)
    print(f"\n✓ get_thread returned thread {fetched.id}")
    print(f"  messages count: {len(fetched.messages)}")

    all_threads = store.list_threads(user_id)
    print(f"\n✓ list_threads returned {len(all_threads)} thread(s):")
    for t in all_threads:
        print(f"  Thread {t.id} — updated: {t.updated_at}")

    # ------------------------------------------------------------------
    # US4: Delete the thread and verify
    # ------------------------------------------------------------------
    store.delete_thread(thread.id, user_id)
    print(f"\n✓ Thread {thread.id} deleted")

    try:
        store.get_thread(thread.id, user_id)
        print("  ✗ ERROR: thread should not exist after deletion")
    except ThreadNotFoundError:
        print("  ✓ Confirmed: ThreadNotFoundError raised as expected")


if __name__ == "__main__":
    main()

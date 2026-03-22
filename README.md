# BYO Thread Storage — Azure Cosmos DB for Foundry Agent

A Python library that provides **Bring Your Own Thread Storage** for Microsoft Foundry Agent, using Azure Cosmos DB for NoSQL as the conversation history backend.

## Overview

By default, Foundry Agent manages conversation history internally. This library lets you take ownership of that storage so you can:

- **Query, audit, and archive** conversation threads
- **Delete** threads on demand (data-retention compliance)
- **Integrate** conversation history into your own application logic

### Architecture

```
Your App
  └── CosmosThreadStore
        └── Azure Cosmos DB for NoSQL
              └── threads container  (partition key: /user_id)
                    └── Thread document  { id, user_id, messages[], ... }
```

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | ≥ 3.11 |
| Azure Cosmos DB for NoSQL | Serverless or ≥ 400 RU/s |
| Azure AI Foundry project | (only for `agent_integration`) |
| Azure CLI / Managed Identity | for `DefaultAzureCredential` |

Your Azure identity needs the **Cosmos DB Built-in Data Contributor** role on the Cosmos DB account.

## Installation

```bash
pip install -r requirements.txt
```

`requirements.txt`:
```
azure-cosmos>=4.7.0
azure-identity
azure-ai-projects
python-dotenv
```

## Environment Variables

Copy `.env.sample` to `.env` and fill in your values:

```bash
cp .env.sample .env
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `COSMOS_ENDPOINT` | ✅ | — | Cosmos DB account endpoint URL |
| `COSMOS_DATABASE_NAME` | ❌ | `thread_storage` | Database name |
| `COSMOS_CONTAINER_NAME` | ❌ | `threads` | Container name |
| `AZURE_AI_PROJECT_ENDPOINT` | ✅* | — | Foundry project endpoint |

*Required only when using `agent_integration`.

## Basic Usage

```python
from dotenv import load_dotenv
from src.config import ThreadStoreConfig
from src.thread_store import CosmosThreadStore

load_dotenv()

# Initialise (auto-creates database and container if absent)
config = ThreadStoreConfig.from_env()
store = CosmosThreadStore(
    endpoint=config.cosmos_endpoint,
    database_name=config.cosmos_database_name,
    container_name=config.cosmos_container_name,
)
store.initialize()

# Create a thread
thread = store.create_thread(user_id="user-001")
print(f"Thread created: {thread.id}")

# Append messages
store.append_message(thread.id, "user-001", "user", "Hello!")
store.append_message(thread.id, "user-001", "assistant", "Hi! How can I help?")

# Retrieve full history
messages = store.get_messages(thread.id, "user-001")
for msg in messages:
    print(f"[{msg.role}] {msg.content}")

# List all threads for a user
threads = store.list_threads("user-001")
for t in threads:
    print(f"Thread {t.id} — updated: {t.updated_at}")

# Delete a thread
store.delete_thread(thread.id, "user-001")
```

## Foundry Agent Integration

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

# Turn 1 — new conversation
reply, thread_id = run_agent_conversation(
    store=store,
    user_id="user-001",
    user_message="I want to plan a trip to Japan.",
)
print(f"Agent: {reply}")

# Turn 2 — continue conversation (agent recalls previous context)
reply, _ = run_agent_conversation(
    store=store,
    user_id="user-001",
    user_message="I prefer Kyoto. Any recommendations?",
    thread_id=thread_id,
)
print(f"Agent: {reply}")
```

## Running the Examples

```bash
# Basic CRUD operations
python examples/basic_usage.py

# Multi-turn Agent conversation
python examples/agent_chat.py
```

## File Structure

```
├── src/
│   ├── __init__.py          # Public API exports
│   ├── models.py            # Thread, Message, ThreadSummary dataclasses
│   ├── exceptions.py        # ThreadStorageError hierarchy
│   ├── config.py            # ThreadStoreConfig + from_env()
│   ├── thread_store.py      # CosmosThreadStore core class
│   └── agent_integration.py # run_agent_conversation() Foundry integration
├── examples/
│   ├── basic_usage.py       # CRUD operation demo
│   └── agent_chat.py        # Multi-turn conversation demo
├── tests/
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── contract/            # Contract tests
├── specs/
│   └── 001-byo-thread-storage/  # Feature specs, plan, data model, contracts
├── .env.sample              # Environment variable template
├── requirements.txt         # Python dependencies
└── pyproject.toml           # Project configuration
```

## Error Handling

| Exception | When raised |
|-----------|-------------|
| `ThreadNotFoundError` | Thread does not exist or belongs to a different user |
| `StorageConnectionError` | Cosmos DB connection or operation failure |
| `AccessDeniedError` | Reserved for future RBAC expansion |
| `ValueError` | Invalid `role` value passed to `append_message` |

```python
from src.exceptions import ThreadNotFoundError, StorageConnectionError

try:
    thread = store.get_thread("non-existent-id", "user-001")
except ThreadNotFoundError as e:
    print(f"Thread not found: {e}")
except StorageConnectionError as e:
    print(f"Storage error: {e}")
```

## Security

- All authentication uses **`DefaultAzureCredential`** — no API keys in code.
- User data isolation is enforced via the **`/user_id` partition key**: a user can only read, update, or delete their own threads.
- Never commit `.env` files; use `.env.sample` as a template.

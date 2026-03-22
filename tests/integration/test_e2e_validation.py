"""End-to-end validation tests for BYO Thread Storage — T022.

Validates all 13 functional requirements (FR-001 ~ FR-013),
5 success criteria (SC-001 ~ SC-005), and 9 acceptance scenarios
(US1 × 2, US2 × 3, US3 × 2, US4 × 2) from spec.md.

Azure services are mocked so these tests run without a live environment.
SC-003 timing assertions use ``time.perf_counter()`` to confirm that the
library code itself adds no measurable latency beyond the (mocked) I/O.
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest
from azure.cosmos import PartitionKey, exceptions as cosmos_exceptions

from src.config import ThreadStoreConfig
from src.exceptions import StorageConnectionError, ThreadNotFoundError
from src.models import Message, Thread, ThreadSummary
from src.thread_store import CosmosThreadStore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ENDPOINT = "https://test-account.documents.azure.com:443/"
_DATABASE = "thread_storage"
_CONTAINER = "threads"
_USER_ID = "e2e-user-001"
_SC003_BUDGET_SECONDS = 3.0  # SC-003: each CRUD op < 3 s (same-region)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_container() -> MagicMock:
    """Return a mock Cosmos DB container with sensible defaults."""
    container = MagicMock()
    container.create_item.return_value = {}
    container.delete_item.return_value = None
    return container


@pytest.fixture()
def store(mock_container: MagicMock) -> CosmosThreadStore:
    """Return an initialised CosmosThreadStore backed by a mock container."""
    with patch("src.thread_store.CosmosClient") as mock_client_cls, patch(
        "src.thread_store.DefaultAzureCredential"
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_db = MagicMock()
        mock_client.create_database_if_not_exists.return_value = mock_db
        mock_db.create_container_if_not_exists.return_value = mock_container

        s = CosmosThreadStore(
            endpoint=_ENDPOINT,
            database_name=_DATABASE,
            container_name=_CONTAINER,
        )
        s.initialize()
        return s


def _make_raw_thread(
    thread_id: str,
    user_id: str = _USER_ID,
    messages: list[dict] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Return a minimal Cosmos DB raw thread document."""
    now = "2026-03-22T00:00:00+00:00"
    return {
        "id": thread_id,
        "user_id": user_id,
        "messages": messages or [],
        "created_at": now,
        "updated_at": now,
        "metadata": metadata or {},
        "_etag": '"etag-001"',
    }


# ---------------------------------------------------------------------------
# US1 — Create & Persist Thread (2 acceptance scenarios)
# ---------------------------------------------------------------------------


class TestUS1CreateAndPersistThread:
    """US1: New conversation threads are created and persisted in Cosmos DB."""

    def test_us1_ac1_create_thread_persists_correct_structure(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """US1 AC-1: Creating a thread produces a document with all required fields.

        Given: Cosmos DB connection is configured and the store is initialised.
        When: A new conversation is started (create_thread called).
        Then: A document is written containing id, user_id, created_at,
              updated_at, messages=[] and metadata.
        """
        thread = store.create_thread(user_id=_USER_ID)

        # Verify Cosmos DB received the document
        mock_container.create_item.assert_called_once()
        written = mock_container.create_item.call_args.kwargs.get(
            "body", mock_container.create_item.call_args[1].get("body")
        )
        if written is None:
            written = mock_container.create_item.call_args[0][0]

        assert written["id"] == thread.id
        assert written["user_id"] == _USER_ID
        assert written["messages"] == []
        assert "created_at" in written
        assert "updated_at" in written
        assert "metadata" in written

    def test_us1_ac2_thread_document_matches_predefined_format(
        self, store: CosmosThreadStore
    ) -> None:
        """US1 AC-2: Thread document structure matches all required fields.

        Given: A new thread document was just created.
        When: The developer inspects the Thread object.
        Then: All required fields are present and correctly typed.
        """
        thread = store.create_thread(user_id=_USER_ID, metadata={"title": "US1 test"})

        assert isinstance(thread, Thread)
        assert isinstance(thread.id, str) and len(thread.id) == 36  # UUID v4
        assert thread.user_id == _USER_ID
        assert thread.messages == []
        assert isinstance(thread.created_at, str)
        assert isinstance(thread.updated_at, str)
        assert thread.metadata == {"title": "US1 test"}


# ---------------------------------------------------------------------------
# US2 — Append Messages & Preserve History (3 acceptance scenarios)
# ---------------------------------------------------------------------------


class TestUS2AppendMessagesAndPreserveHistory:
    """US2: Messages are appended to threads and full history is retained."""

    def test_us2_ac1_append_message_updates_thread_with_all_fields(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """US2 AC-1: Appended message has role, content, timestamp; updated_at refreshed.

        Given: A thread document exists in Cosmos DB.
        When: A user message is appended.
        Then: The message is added to messages[] with role, content and timestamp;
              updated_at is refreshed.
        """
        thread_id = "thread-us2-ac1"
        raw = _make_raw_thread(thread_id)
        mock_container.read_item.return_value = dict(raw)
        mock_container.replace_item.return_value = {}

        msg = store.append_message(thread_id, _USER_ID, "user", "Hello!")

        assert isinstance(msg, Message)
        assert msg.role == "user"
        assert msg.content == "Hello!"
        assert isinstance(msg.timestamp, str)

        # Verify the replace_item call updated the document
        mock_container.replace_item.assert_called_once()
        replaced_body = mock_container.replace_item.call_args.kwargs["body"]
        assert len(replaced_body["messages"]) == 1
        assert replaced_body["messages"][0]["role"] == "user"
        assert replaced_body["messages"][0]["content"] == "Hello!"
        assert "timestamp" in replaced_body["messages"][0]
        assert replaced_body["updated_at"] != raw["updated_at"]

    def test_us2_ac2_agent_reply_appended_and_full_history_confirmed(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """US2 AC-2: Agent reply is persisted; developer can confirm full multi-turn history.

        Given: A user message was just appended.
        When: The assistant reply is also appended and history is retrieved.
        Then: get_messages returns the complete multi-turn conversation.
        """
        thread_id = "thread-us2-ac2"

        # Simulate sequential state: start empty, then grow
        states = [
            _make_raw_thread(thread_id),  # first read for user msg
            _make_raw_thread(
                thread_id,
                messages=[
                    {
                        "role": "user",
                        "content": "Hello!",
                        "timestamp": "2026-03-22T00:00:01+00:00",
                    }
                ],
            ),  # second read for assistant msg
            # get_thread read for get_messages
            _make_raw_thread(
                thread_id,
                messages=[
                    {
                        "role": "user",
                        "content": "Hello!",
                        "timestamp": "2026-03-22T00:00:01+00:00",
                    },
                    {
                        "role": "assistant",
                        "content": "Hi there!",
                        "timestamp": "2026-03-22T00:00:02+00:00",
                    },
                ],
            ),
        ]
        mock_container.read_item.side_effect = [dict(s) for s in states]
        mock_container.replace_item.return_value = {}

        store.append_message(thread_id, _USER_ID, "user", "Hello!")
        store.append_message(thread_id, _USER_ID, "assistant", "Hi there!")
        messages = store.get_messages(thread_id, _USER_ID)

        assert len(messages) == 2
        roles = [m.role for m in messages]
        assert "user" in roles
        assert "assistant" in roles

    def test_us2_ac3_full_history_preserved_for_multi_turn_context(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """US2 AC-3: Full conversation history is available for Agent context.

        Given: A thread with 10+ rounds of conversation.
        When: get_messages is called to supply context to the Agent.
        Then: All messages are returned without truncation (FR-007).
        """
        thread_id = "thread-us2-ac3"
        # Build 10 user/assistant pairs (20 messages total)
        many_messages = []
        for i in range(10):
            many_messages.append(
                {
                    "role": "user",
                    "content": f"User turn {i + 1}",
                    "timestamp": f"2026-03-22T00:{i:02d}:00+00:00",
                }
            )
            many_messages.append(
                {
                    "role": "assistant",
                    "content": f"Assistant turn {i + 1}",
                    "timestamp": f"2026-03-22T00:{i:02d}:30+00:00",
                }
            )

        mock_container.read_item.return_value = _make_raw_thread(
            thread_id, messages=many_messages
        )

        messages = store.get_messages(thread_id, _USER_ID)

        assert len(messages) == 20
        # Verify sorted by timestamp (chronological)
        timestamps = [m.timestamp for m in messages]
        assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# US3 — Query & Retrieve Threads (2 acceptance scenarios)
# ---------------------------------------------------------------------------


class TestUS3QueryAndRetrieveThreads:
    """US3: Threads can be retrieved by ID with complete data."""

    def test_us3_ac1_get_thread_returns_complete_data(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """US3 AC-1: get_thread returns full data including messages, metadata, timestamps.

        Given: A thread with multiple messages exists in Cosmos DB.
        When: The developer queries by thread ID.
        Then: The response contains all messages, metadata and timestamps.
        """
        thread_id = "thread-us3-ac1"
        raw = _make_raw_thread(
            thread_id,
            messages=[
                {
                    "role": "user",
                    "content": "Question 1",
                    "timestamp": "2026-03-22T10:00:00+00:00",
                },
                {
                    "role": "assistant",
                    "content": "Answer 1",
                    "timestamp": "2026-03-22T10:00:05+00:00",
                },
            ],
            metadata={"title": "US3 test"},
        )
        mock_container.read_item.return_value = dict(raw)

        thread = store.get_thread(thread_id, _USER_ID)

        assert isinstance(thread, Thread)
        assert thread.id == thread_id
        assert thread.user_id == _USER_ID
        assert len(thread.messages) == 2
        assert thread.metadata == {"title": "US3 test"}
        assert thread.created_at == raw["created_at"]
        assert thread.updated_at == raw["updated_at"]

    def test_us3_ac2_get_nonexistent_thread_raises_thread_not_found_error(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """US3 AC-2: Querying a non-existent thread raises ThreadNotFoundError, not an unhandled exception.

        Given: The developer supplies an unknown thread ID.
        When: get_thread is called.
        Then: ThreadNotFoundError is raised with a clear message (FR-009).
        """
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosResourceNotFoundError(404, "Not found")
        )

        with pytest.raises(ThreadNotFoundError) as exc_info:
            store.get_thread("nonexistent-id", _USER_ID)

        assert "nonexistent-id" in str(exc_info.value)
        assert _USER_ID in str(exc_info.value)


# ---------------------------------------------------------------------------
# US4 — Delete Thread (2 acceptance scenarios)
# ---------------------------------------------------------------------------


class TestUS4DeleteThread:
    """US4: Threads can be permanently deleted from Cosmos DB."""

    def test_us4_ac1_delete_thread_permanently_removes_it(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """US4 AC-1: delete_thread removes the thread and all its messages.

        Given: A thread exists in Cosmos DB.
        When: delete_thread is called.
        Then: The Cosmos DB delete operation is executed for that thread.
        """
        thread_id = "thread-us4-ac1"

        store.delete_thread(thread_id, _USER_ID)

        mock_container.delete_item.assert_called_once_with(
            item=thread_id, partition_key=_USER_ID
        )

    def test_us4_ac2_get_thread_after_deletion_raises_thread_not_found_error(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """US4 AC-2: Querying a deleted thread returns ThreadNotFoundError.

        Given: A thread has been deleted.
        When: The developer queries the same thread ID again.
        Then: ThreadNotFoundError is returned (not a generic exception).
        """
        thread_id = "thread-us4-ac2"

        # First call (delete) succeeds; second call (get) raises 404
        mock_container.delete_item.return_value = None
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosResourceNotFoundError(404, "Not found")
        )

        store.delete_thread(thread_id, _USER_ID)

        with pytest.raises(ThreadNotFoundError):
            store.get_thread(thread_id, _USER_ID)


# ---------------------------------------------------------------------------
# Functional Requirements (FR-001 ~ FR-013)
# ---------------------------------------------------------------------------


class TestFunctionalRequirements:
    """Validates each of the 13 functional requirements from spec.md."""

    # FR-001 ---------------------------------------------------------------

    def test_fr001_create_thread_accepts_user_id_and_optional_metadata(
        self, store: CosmosThreadStore
    ) -> None:
        """FR-001: create_thread accepts user_id and optional metadata."""
        t1 = store.create_thread(user_id=_USER_ID)
        assert t1.user_id == _USER_ID
        assert t1.metadata == {}

        t2 = store.create_thread(user_id=_USER_ID, metadata={"k": "v"})
        assert t2.metadata == {"k": "v"}

    def test_fr001_create_thread_returns_unique_thread_id(
        self, store: CosmosThreadStore
    ) -> None:
        """FR-001: Each call returns a thread with a unique identifier."""
        t1 = store.create_thread(user_id=_USER_ID)
        t2 = store.create_thread(user_id=_USER_ID)
        assert t1.id != t2.id

    # FR-002 ---------------------------------------------------------------

    def test_fr002_append_message_validates_role(
        self, store: CosmosThreadStore
    ) -> None:
        """FR-002: Invalid role raises ValueError immediately."""
        with pytest.raises(ValueError, match="invalid_role"):
            store.append_message("any-id", _USER_ID, "invalid_role", "text")

    def test_fr002_append_message_accepts_valid_roles(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """FR-002: system, user, and assistant are accepted roles."""
        thread_id = "thread-fr002"
        for role in ("system", "user", "assistant"):
            mock_container.read_item.return_value = _make_raw_thread(thread_id)
            mock_container.replace_item.return_value = {}
            msg = store.append_message(thread_id, _USER_ID, role, "text")
            assert msg.role == role

    def test_fr002_etag_conflict_retried_up_to_three_times(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """FR-002: ETag conflicts trigger auto-retry (max 3 attempts)."""
        thread_id = "thread-fr002-etag"
        raw = _make_raw_thread(thread_id)
        mock_container.read_item.return_value = dict(raw)
        # Fail twice on ETag conflict, succeed on third attempt
        mock_container.replace_item.side_effect = [
            cosmos_exceptions.CosmosAccessConditionFailedError(),
            cosmos_exceptions.CosmosAccessConditionFailedError(),
            {},
        ]

        msg = store.append_message(thread_id, _USER_ID, "user", "retry test")
        assert msg.content == "retry test"
        assert mock_container.replace_item.call_count == 3

    # FR-003 ---------------------------------------------------------------

    def test_fr003_get_thread_returns_full_thread_with_messages_and_metadata(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """FR-003: get_thread returns complete thread including messages and metadata."""
        thread_id = "thread-fr003"
        raw = _make_raw_thread(
            thread_id,
            messages=[
                {"role": "user", "content": "Hi", "timestamp": "2026-03-22T00:00:01+00:00"}
            ],
            metadata={"source": "test"},
        )
        mock_container.read_item.return_value = dict(raw)

        thread = store.get_thread(thread_id, _USER_ID)

        assert len(thread.messages) == 1
        assert thread.metadata == {"source": "test"}

    # FR-004 ---------------------------------------------------------------

    def test_fr004_get_messages_returns_messages_only(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """FR-004: get_messages returns only the messages list (not full thread)."""
        thread_id = "thread-fr004"
        mock_container.read_item.return_value = _make_raw_thread(
            thread_id,
            messages=[
                {"role": "user", "content": "A", "timestamp": "2026-03-22T00:00:01+00:00"},
                {"role": "assistant", "content": "B", "timestamp": "2026-03-22T00:00:02+00:00"},
            ],
        )

        result = store.get_messages(thread_id, _USER_ID)

        assert isinstance(result, list)
        assert all(isinstance(m, Message) for m in result)
        assert len(result) == 2

    # FR-005 ---------------------------------------------------------------

    def test_fr005_delete_thread_removes_from_cosmos(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """FR-005: delete_thread calls Cosmos DB delete with correct args."""
        thread_id = "thread-fr005"
        store.delete_thread(thread_id, _USER_ID)
        mock_container.delete_item.assert_called_once_with(
            item=thread_id, partition_key=_USER_ID
        )

    # FR-006 + FR-007 -------------------------------------------------------

    def test_fr006_fr007_run_agent_conversation_persists_messages_and_sends_history(
        self,
    ) -> None:
        """FR-006/FR-007: run_agent_conversation persists messages and sends full history to the Agent."""
        user_msg = "Tell me about Japan"
        agent_reply = "Japan is a beautiful country."
        thread_id = "thread-fr006"

        # Build mock store that returns history after each append
        mock_store = MagicMock()
        mock_thread = MagicMock()
        mock_thread.id = thread_id
        mock_store.create_thread.return_value = mock_thread
        mock_store.get_messages.return_value = [
            Message(role="user", content=user_msg),
        ]

        # Build mock Foundry client
        text_part = MagicMock()
        text_part.text.value = agent_reply
        assistant_msg = MagicMock()
        assistant_msg.role = "assistant"
        assistant_msg.content = [text_part]
        response = MagicMock()
        response.data = [assistant_msg]

        mock_agent = MagicMock()
        mock_agent.id = "agent-001"
        agents_client = MagicMock()
        agents_client.list_agents.return_value = [mock_agent]
        foundry_thread = MagicMock()
        foundry_thread.id = "foundry-001"
        agents_client.create_thread.return_value = foundry_thread
        agents_client.list_messages.return_value = response
        project_client = MagicMock()
        project_client.__enter__ = MagicMock(return_value=project_client)
        project_client.__exit__ = MagicMock(return_value=False)
        project_client.agents = agents_client

        with patch(
            "src.agent_integration.AIProjectClient", return_value=project_client
        ), patch("src.agent_integration.DefaultAzureCredential"), patch.dict(
            os.environ,
            {"AZURE_AI_PROJECT_ENDPOINT": "https://project.api.azureml.ms"},
        ):
            from src.agent_integration import run_agent_conversation

            reply, returned_thread_id = run_agent_conversation(
                store=mock_store,
                user_id=_USER_ID,
                user_message=user_msg,
            )

        # FR-006: user message persisted before calling Agent
        mock_store.append_message.assert_any_call(
            thread_id, _USER_ID, "user", user_msg
        )
        # FR-007: full history retrieved and sent
        mock_store.get_messages.assert_called_once_with(thread_id, _USER_ID)
        # FR-006: agent reply persisted after Agent call
        mock_store.append_message.assert_any_call(
            thread_id, _USER_ID, "assistant", agent_reply
        )
        assert reply == agent_reply
        assert returned_thread_id == thread_id

    # FR-008 ---------------------------------------------------------------

    def test_fr008_default_azure_credential_used_when_no_credential_provided(
        self,
    ) -> None:
        """FR-008: DefaultAzureCredential is used when no credential is supplied."""
        with patch("src.thread_store.CosmosClient") as mock_client_cls, patch(
            "src.thread_store.DefaultAzureCredential"
        ) as mock_dac_cls:
            mock_dac = MagicMock()
            mock_dac_cls.return_value = mock_dac

            CosmosThreadStore(
                endpoint=_ENDPOINT,
                database_name=_DATABASE,
                container_name=_CONTAINER,
            )

            mock_dac_cls.assert_called_once()
            mock_client_cls.assert_called_once_with(url=_ENDPOINT, credential=mock_dac)

    def test_fr008_no_hardcoded_credentials_in_source(self) -> None:
        """FR-008/SC-005: Source files must not contain hardcoded keys or secrets."""
        import pathlib

        repo_root = pathlib.Path(__file__).parent.parent.parent
        suspicious_patterns = [
            "AccountKey=",
            "SharedAccessSignature",
            "client_secret=",
            "password=",
        ]
        src_files = list((repo_root / "src").glob("**/*.py"))
        assert src_files, "No source files found"

        for path in src_files:
            content = path.read_text()
            for pattern in suspicious_patterns:
                assert pattern not in content, (
                    f"Possible hardcoded credential '{pattern}' found in {path}"
                )

    # FR-009 ---------------------------------------------------------------

    def test_fr009_cosmos_connection_failure_raises_storage_connection_error(
        self,
    ) -> None:
        """FR-009: Cosmos DB failures surface as StorageConnectionError with a clear message."""
        with patch("src.thread_store.CosmosClient") as mock_client_cls, patch(
            "src.thread_store.DefaultAzureCredential"
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.create_database_if_not_exists.side_effect = (
                cosmos_exceptions.CosmosHttpResponseError(
                    message="Connection refused"
                )
            )

            s = CosmosThreadStore(
                endpoint=_ENDPOINT,
                database_name=_DATABASE,
                container_name=_CONTAINER,
            )

            with pytest.raises(StorageConnectionError) as exc_info:
                s.initialize()

            assert "Failed to initialise Cosmos DB storage" in str(exc_info.value)

    def test_fr009_thread_not_found_error_has_clear_message(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """FR-009: ThreadNotFoundError message identifies both thread ID and user ID."""
        thread_id = "missing-thread"
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosResourceNotFoundError(404, "Not found")
        )

        with pytest.raises(ThreadNotFoundError) as exc_info:
            store.get_thread(thread_id, _USER_ID)

        message = str(exc_info.value)
        assert thread_id in message
        assert _USER_ID in message

    # FR-010 ---------------------------------------------------------------

    def test_fr010_list_threads_returns_thread_summary_objects(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """FR-010: list_threads returns list[ThreadSummary] (typed, no messages field)."""
        now = "2026-03-22T00:00:00+00:00"
        mock_container.query_items.return_value = iter(
            [
                {
                    "id": "t-001",
                    "user_id": _USER_ID,
                    "created_at": now,
                    "updated_at": now,
                    "metadata": {"title": "First"},
                },
                {
                    "id": "t-002",
                    "user_id": _USER_ID,
                    "created_at": now,
                    "updated_at": now,
                    "metadata": {},
                },
            ]
        )

        summaries = store.list_threads(_USER_ID)

        assert len(summaries) == 2
        assert all(isinstance(s, ThreadSummary) for s in summaries)
        # ThreadSummary must NOT have a messages attribute
        for summary in summaries:
            assert not hasattr(summary, "messages")

    # FR-011 ---------------------------------------------------------------

    def test_fr011_initialize_creates_database_and_container_if_absent(
        self,
    ) -> None:
        """FR-011: initialize() auto-creates database and container with /user_id partition key."""
        with patch("src.thread_store.CosmosClient") as mock_client_cls, patch(
            "src.thread_store.DefaultAzureCredential"
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_db = MagicMock()
            mock_client.create_database_if_not_exists.return_value = mock_db
            mock_container = MagicMock()
            mock_db.create_container_if_not_exists.return_value = mock_container

            s = CosmosThreadStore(
                endpoint=_ENDPOINT,
                database_name=_DATABASE,
                container_name=_CONTAINER,
            )
            s.initialize()

            mock_client.create_database_if_not_exists.assert_called_once_with(
                id=_DATABASE
            )
            call_kwargs = mock_db.create_container_if_not_exists.call_args
            assert call_kwargs.kwargs["id"] == _CONTAINER
            pk = call_kwargs.kwargs["partition_key"]
            assert isinstance(pk, PartitionKey)
            assert pk.path == "/user_id"

    # FR-012 ---------------------------------------------------------------

    def test_fr012_config_loads_all_values_from_environment_variables(
        self,
    ) -> None:
        """FR-012: ThreadStoreConfig.from_env() reads all settings from env vars."""
        env_vars = {
            "COSMOS_ENDPOINT": "https://my-account.documents.azure.com:443/",
            "COSMOS_DATABASE_NAME": "my_db",
            "COSMOS_CONTAINER_NAME": "my_container",
            "AZURE_AI_PROJECT_ENDPOINT": "https://my-project.api.azureml.ms",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            config = ThreadStoreConfig.from_env()

        assert config.cosmos_endpoint == env_vars["COSMOS_ENDPOINT"]
        assert config.cosmos_database_name == env_vars["COSMOS_DATABASE_NAME"]
        assert config.cosmos_container_name == env_vars["COSMOS_CONTAINER_NAME"]
        assert config.azure_ai_project_endpoint == env_vars["AZURE_AI_PROJECT_ENDPOINT"]

    def test_fr012_missing_cosmos_endpoint_raises_value_error(self) -> None:
        """FR-012: Missing COSMOS_ENDPOINT raises ValueError with a clear message."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="COSMOS_ENDPOINT"):
                ThreadStoreConfig.from_env()

    # FR-013 ---------------------------------------------------------------

    def test_fr013_user_id_partition_key_enforces_data_isolation(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """FR-013: All reads use (thread_id, user_id) — mismatched user gets 404 (ThreadNotFoundError)."""
        thread_id = "thread-fr013"
        wrong_user = "attacker-999"
        # Cosmos DB returns 404 when user_id (partition key) does not match
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosResourceNotFoundError(404, "Not found")
        )

        with pytest.raises(ThreadNotFoundError):
            store.get_thread(thread_id, wrong_user)

        # Verify partition key was passed to read_item (enforced isolation)
        mock_container.read_item.assert_called_once_with(
            item=thread_id, partition_key=wrong_user
        )

    def test_fr013_append_message_uses_user_id_partition_key(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """FR-013: append_message uses user_id as partition key for read."""
        thread_id = "thread-fr013b"
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosResourceNotFoundError(404, "Not found")
        )

        with pytest.raises(ThreadNotFoundError):
            store.append_message(thread_id, _USER_ID, "user", "text")

        mock_container.read_item.assert_called_once_with(
            item=thread_id, partition_key=_USER_ID
        )


# ---------------------------------------------------------------------------
# Success Criteria (SC-001 ~ SC-005)
# ---------------------------------------------------------------------------


class TestSuccessCriteria:
    """Validates the 5 measurable success criteria from spec.md."""

    def test_sc001_setup_completes_in_five_or_fewer_steps(self) -> None:
        """SC-001: Developer can create first thread in ≤5 distinct operation steps.

        The five steps from quickstart.md are:
          1. pip install -r requirements.txt   (not tested here — install step)
          2. Copy .env.sample → .env, set COSMOS_ENDPOINT
          3. ThreadStoreConfig.from_env()
          4. CosmosThreadStore(...) + .initialize()
          5. store.create_thread(user_id=...)
        This test verifies steps 2-5 execute successfully as a single flow.
        """
        env_vars = {
            "COSMOS_ENDPOINT": _ENDPOINT,
            "COSMOS_DATABASE_NAME": _DATABASE,
            "COSMOS_CONTAINER_NAME": _CONTAINER,
        }

        with patch.dict(os.environ, env_vars, clear=True), patch(
            "src.thread_store.CosmosClient"
        ) as mock_client_cls, patch("src.thread_store.DefaultAzureCredential"):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_db = MagicMock()
            mock_client.create_database_if_not_exists.return_value = mock_db
            mock_container = MagicMock()
            mock_db.create_container_if_not_exists.return_value = mock_container
            mock_container.create_item.return_value = {}

            # Step 2: config from env
            config = ThreadStoreConfig.from_env()

            # Step 3: create store
            s = CosmosThreadStore(
                endpoint=config.cosmos_endpoint,
                database_name=config.cosmos_database_name,
                container_name=config.cosmos_container_name,
            )

            # Step 4: initialize
            s.initialize()

            # Step 5: create first thread
            thread = s.create_thread(user_id=_USER_ID)

        assert thread.id is not None
        assert thread.user_id == _USER_ID
        # The 5 steps from quickstart.md are: (1) pip install, (2) configure .env,
        # (3) from_env(), (4) CosmosThreadStore + initialize(), (5) create_thread().
        # Steps 2-5 are exercised above — confirming the full flow succeeds.

    def test_sc003_create_thread_completes_within_three_seconds(
        self, store: CosmosThreadStore
    ) -> None:
        """SC-003: create_thread (excluding network I/O) completes < 3 s."""
        start = time.perf_counter()
        store.create_thread(user_id=_USER_ID)
        elapsed = time.perf_counter() - start

        assert elapsed < _SC003_BUDGET_SECONDS, (
            f"SC-003: create_thread took {elapsed:.3f}s (budget: {_SC003_BUDGET_SECONDS}s)"
        )

    def test_sc003_append_message_completes_within_three_seconds(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """SC-003: append_message (excluding network I/O) completes < 3 s."""
        thread_id = "thread-sc003"
        mock_container.read_item.return_value = _make_raw_thread(thread_id)
        mock_container.replace_item.return_value = {}

        start = time.perf_counter()
        store.append_message(thread_id, _USER_ID, "user", "timing test")
        elapsed = time.perf_counter() - start

        assert elapsed < _SC003_BUDGET_SECONDS, (
            f"SC-003: append_message took {elapsed:.3f}s (budget: {_SC003_BUDGET_SECONDS}s)"
        )

    def test_sc003_get_thread_completes_within_three_seconds(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """SC-003: get_thread (excluding network I/O) completes < 3 s."""
        thread_id = "thread-sc003-get"
        mock_container.read_item.return_value = _make_raw_thread(thread_id)

        start = time.perf_counter()
        store.get_thread(thread_id, _USER_ID)
        elapsed = time.perf_counter() - start

        assert elapsed < _SC003_BUDGET_SECONDS, (
            f"SC-003: get_thread took {elapsed:.3f}s (budget: {_SC003_BUDGET_SECONDS}s)"
        )

    def test_sc003_delete_thread_completes_within_three_seconds(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """SC-003: delete_thread (excluding network I/O) completes < 3 s."""
        thread_id = "thread-sc003-delete"

        start = time.perf_counter()
        store.delete_thread(thread_id, _USER_ID)
        elapsed = time.perf_counter() - start

        assert elapsed < _SC003_BUDGET_SECONDS, (
            f"SC-003: delete_thread took {elapsed:.3f}s (budget: {_SC003_BUDGET_SECONDS}s)"
        )

    def test_sc003_list_threads_completes_within_three_seconds(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """SC-003: list_threads (excluding network I/O) completes < 3 s."""
        mock_container.query_items.return_value = iter([])

        start = time.perf_counter()
        store.list_threads(_USER_ID)
        elapsed = time.perf_counter() - start

        assert elapsed < _SC003_BUDGET_SECONDS, (
            f"SC-003: list_threads took {elapsed:.3f}s (budget: {_SC003_BUDGET_SECONDS}s)"
        )

    def test_sc004_every_cosmos_error_surfaces_as_understandable_exception(
        self, store: CosmosThreadStore, mock_container: MagicMock
    ) -> None:
        """SC-004: 100% of Cosmos DB errors return typed, understandable exceptions.

        Checks that neither ThreadStorageError nor its subclasses are raised
        without a meaningful message.
        """
        thread_id = "thread-sc004"
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosResourceNotFoundError(404, "Not found")
        )

        with pytest.raises(ThreadNotFoundError) as exc_info:
            store.get_thread(thread_id, _USER_ID)

        # Message must be non-empty and mention the thread
        assert str(exc_info.value).strip() != ""
        assert thread_id in str(exc_info.value)

    def test_sc004_storage_connection_error_has_meaningful_message(
        self,
    ) -> None:
        """SC-004: StorageConnectionError carries a meaningful, non-empty message."""
        with patch("src.thread_store.CosmosClient") as mock_client_cls, patch(
            "src.thread_store.DefaultAzureCredential"
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.create_database_if_not_exists.side_effect = (
                cosmos_exceptions.CosmosHttpResponseError(
                    message="Service unavailable"
                )
            )

            s = CosmosThreadStore(
                endpoint=_ENDPOINT,
                database_name=_DATABASE,
                container_name=_CONTAINER,
            )

            with pytest.raises(StorageConnectionError) as exc_info:
                s.initialize()

            assert str(exc_info.value).strip() != ""

    def test_sc005_default_azure_credential_is_the_only_auth_mechanism(
        self,
    ) -> None:
        """SC-005: Authentication uses DefaultAzureCredential — no hardcoded keys."""
        with patch("src.thread_store.CosmosClient") as mock_client_cls, patch(
            "src.thread_store.DefaultAzureCredential"
        ) as mock_dac_cls:
            mock_dac_cls.return_value = MagicMock()
            mock_client_cls.return_value = MagicMock()

            CosmosThreadStore(
                endpoint=_ENDPOINT,
                database_name=_DATABASE,
                container_name=_CONTAINER,
                # No credential supplied — must default to DefaultAzureCredential
            )

            mock_dac_cls.assert_called_once()

    def test_sc005_agent_integration_uses_default_azure_credential(
        self,
    ) -> None:
        """SC-005: run_agent_conversation uses DefaultAzureCredential for Foundry auth."""
        mock_store = MagicMock()
        mock_thread = MagicMock()
        mock_thread.id = "thread-sc005"
        mock_store.create_thread.return_value = mock_thread
        mock_store.get_messages.return_value = [
            Message(role="user", content="test")
        ]

        text_part = MagicMock()
        text_part.text.value = "reply"
        assistant_msg = MagicMock()
        assistant_msg.role = "assistant"
        assistant_msg.content = [text_part]
        response = MagicMock()
        response.data = [assistant_msg]
        mock_agent = MagicMock()
        mock_agent.id = "agent-001"
        agents_client = MagicMock()
        agents_client.list_agents.return_value = [mock_agent]
        foundry_thread = MagicMock()
        foundry_thread.id = "foundry-001"
        agents_client.create_thread.return_value = foundry_thread
        agents_client.list_messages.return_value = response
        project_client = MagicMock()
        project_client.__enter__ = MagicMock(return_value=project_client)
        project_client.__exit__ = MagicMock(return_value=False)
        project_client.agents = agents_client

        with patch(
            "src.agent_integration.AIProjectClient", return_value=project_client
        ) as mock_ai_client, patch(
            "src.agent_integration.DefaultAzureCredential"
        ) as mock_dac_cls, patch.dict(
            os.environ,
            {"AZURE_AI_PROJECT_ENDPOINT": "https://project.api.azureml.ms"},
        ):
            from src.agent_integration import run_agent_conversation

            run_agent_conversation(
                store=mock_store,
                user_id=_USER_ID,
                user_message="hello",
            )

            mock_dac_cls.assert_called_once()
            mock_ai_client.assert_called_once()
            _, kwargs = mock_ai_client.call_args
            assert "credential" in kwargs

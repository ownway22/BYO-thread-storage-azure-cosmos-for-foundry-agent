"""Unit tests for CosmosThreadStore.__init__(), initialize(), create_thread(), append_message(), get_messages(), get_thread(), and list_threads() — T008/T009/T011/T012/T015/T016."""

from unittest.mock import MagicMock, call, patch

import pytest
from azure.cosmos import PartitionKey, exceptions as cosmos_exceptions

from src.exceptions import StorageConnectionError, ThreadNotFoundError
from src.models import Message, Thread, ThreadSummary
from src.thread_store import CosmosThreadStore, _MAX_ETAG_RETRIES


_ENDPOINT = "https://test-account.documents.azure.com:443/"
_DATABASE = "thread_storage"
_CONTAINER = "threads"


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestCosmosThreadStoreInit:
    """Tests for CosmosThreadStore.__init__()."""

    @patch("src.thread_store.CosmosClient")
    @patch("src.thread_store.DefaultAzureCredential")
    def test_defaults_to_default_azure_credential(
        self, mock_dac_cls: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        """FR-008: DefaultAzureCredential is used when no credential is passed."""
        mock_dac = MagicMock()
        mock_dac_cls.return_value = mock_dac

        store = CosmosThreadStore(
            endpoint=_ENDPOINT,
            database_name=_DATABASE,
            container_name=_CONTAINER,
        )

        mock_dac_cls.assert_called_once()
        mock_client_cls.assert_called_once_with(
            url=_ENDPOINT, credential=mock_dac
        )
        assert store._credential is mock_dac

    @patch("src.thread_store.CosmosClient")
    def test_custom_credential_is_used_when_provided(
        self, mock_client_cls: MagicMock
    ) -> None:
        """A caller-supplied credential bypasses DefaultAzureCredential."""
        custom_cred = MagicMock()

        store = CosmosThreadStore(
            endpoint=_ENDPOINT,
            database_name=_DATABASE,
            container_name=_CONTAINER,
            credential=custom_cred,
        )

        mock_client_cls.assert_called_once_with(
            url=_ENDPOINT, credential=custom_cred
        )
        assert store._credential is custom_cred

    @patch("src.thread_store.CosmosClient")
    @patch("src.thread_store.DefaultAzureCredential")
    def test_cosmos_client_singleton_is_created_once(
        self, _mock_dac: MagicMock, mock_client_cls: MagicMock
    ) -> None:
        """Singleton pattern: CosmosClient is instantiated exactly once in __init__."""
        CosmosThreadStore(
            endpoint=_ENDPOINT,
            database_name=_DATABASE,
            container_name=_CONTAINER,
        )
        assert mock_client_cls.call_count == 1

    @patch("src.thread_store.CosmosClient")
    @patch("src.thread_store.DefaultAzureCredential")
    def test_endpoint_and_names_stored(
        self, _mock_dac: MagicMock, _mock_client: MagicMock
    ) -> None:
        """Constructor stores endpoint, database_name, and container_name."""
        store = CosmosThreadStore(
            endpoint=_ENDPOINT,
            database_name="my_db",
            container_name="my_container",
        )
        assert store._endpoint == _ENDPOINT
        assert store._database_name == "my_db"
        assert store._container_name == "my_container"

    @patch("src.thread_store.CosmosClient")
    @patch("src.thread_store.DefaultAzureCredential")
    def test_container_is_none_before_initialize(
        self, _mock_dac: MagicMock, _mock_client: MagicMock
    ) -> None:
        """Container reference is None until initialize() is called."""
        store = CosmosThreadStore(
            endpoint=_ENDPOINT,
            database_name=_DATABASE,
            container_name=_CONTAINER,
        )
        assert store._container is None


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------


class TestCosmosThreadStoreInitialize:
    """Tests for CosmosThreadStore.initialize() — FR-011."""

    def _make_store(self) -> tuple[CosmosThreadStore, MagicMock]:
        """Return a store instance with a fully mocked CosmosClient."""
        mock_client = MagicMock()
        with patch("src.thread_store.DefaultAzureCredential"), patch(
            "src.thread_store.CosmosClient", return_value=mock_client
        ):
            store = CosmosThreadStore(
                endpoint=_ENDPOINT,
                database_name=_DATABASE,
                container_name=_CONTAINER,
            )
        return store, mock_client

    def test_creates_database_if_not_exists(self) -> None:
        """initialize() calls create_database_if_not_exists with the database name."""
        store, mock_client = self._make_store()
        mock_db = MagicMock()
        mock_client.create_database_if_not_exists.return_value = mock_db

        store.initialize()

        mock_client.create_database_if_not_exists.assert_called_once_with(
            id=_DATABASE
        )

    def test_creates_container_if_not_exists_with_partition_key(self) -> None:
        """initialize() creates the container with partition key /user_id."""
        store, mock_client = self._make_store()
        mock_db = MagicMock()
        mock_client.create_database_if_not_exists.return_value = mock_db

        store.initialize()

        call_kwargs = mock_db.create_container_if_not_exists.call_args
        assert call_kwargs.kwargs["id"] == _CONTAINER
        pk: PartitionKey = call_kwargs.kwargs["partition_key"]
        assert pk["paths"] == ["/user_id"]

    def test_container_reference_set_after_initialize(self) -> None:
        """initialize() sets _container to the returned container proxy."""
        store, mock_client = self._make_store()
        mock_db = MagicMock()
        mock_container = MagicMock()
        mock_client.create_database_if_not_exists.return_value = mock_db
        mock_db.create_container_if_not_exists.return_value = mock_container

        store.initialize()

        assert store._container is mock_container

    def test_raises_storage_connection_error_on_cosmos_http_error(self) -> None:
        """CosmosHttpResponseError during initialize() → StorageConnectionError."""
        store, mock_client = self._make_store()
        mock_client.create_database_if_not_exists.side_effect = (
            cosmos_exceptions.CosmosHttpResponseError(message="Service unavailable")
        )

        with pytest.raises(StorageConnectionError):
            store.initialize()

    def test_raises_storage_connection_error_on_generic_exception(self) -> None:
        """Any unexpected exception during initialize() → StorageConnectionError."""
        store, mock_client = self._make_store()
        mock_client.create_database_if_not_exists.side_effect = OSError(
            "Network unreachable"
        )

        with pytest.raises(StorageConnectionError):
            store.initialize()

    def test_storage_connection_error_message_contains_detail(self) -> None:
        """StorageConnectionError preserves diagnostic detail from the source."""
        store, mock_client = self._make_store()
        mock_client.create_database_if_not_exists.side_effect = OSError(
            "timeout exceeded"
        )

        with pytest.raises(StorageConnectionError, match="timeout exceeded"):
            store.initialize()

    def test_storage_connection_error_chains_original_exception(self) -> None:
        """StorageConnectionError is raised 'from' the original exception (chained)."""
        store, mock_client = self._make_store()
        original = OSError("original error")
        mock_client.create_database_if_not_exists.side_effect = original

        with pytest.raises(StorageConnectionError) as exc_info:
            store.initialize()

        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# create_thread()
# ---------------------------------------------------------------------------


class TestCosmosThreadStoreCreateThread:
    """Tests for CosmosThreadStore.create_thread() — FR-001 / T009."""

    def _make_initialized_store(self) -> tuple[CosmosThreadStore, MagicMock]:
        """Return a store with a mocked CosmosClient and container already set."""
        mock_client = MagicMock()
        mock_container = MagicMock()
        with patch("src.thread_store.DefaultAzureCredential"), patch(
            "src.thread_store.CosmosClient", return_value=mock_client
        ):
            store = CosmosThreadStore(
                endpoint=_ENDPOINT,
                database_name=_DATABASE,
                container_name=_CONTAINER,
            )
        # Simulate post-initialize() state
        store._container = mock_container
        return store, mock_container

    def test_returns_thread_object(self) -> None:
        """create_thread() returns a Thread instance."""
        store, _ = self._make_initialized_store()

        result = store.create_thread(user_id="user-001")

        assert isinstance(result, Thread)

    def test_thread_has_correct_structure(self) -> None:
        """Returned Thread contains id, user_id, messages=[], created_at, updated_at, metadata."""
        store, _ = self._make_initialized_store()

        thread = store.create_thread(user_id="user-001")

        assert thread.user_id == "user-001"
        assert thread.id  # non-empty UUID string
        assert thread.messages == []
        assert thread.created_at
        assert thread.updated_at
        assert isinstance(thread.metadata, dict)

    def test_calls_create_item_with_serialized_thread(self) -> None:
        """create_thread() calls container.create_item with thread.to_dict()."""
        store, mock_container = self._make_initialized_store()

        thread = store.create_thread(user_id="user-001")

        mock_container.create_item.assert_called_once_with(
            body=thread.to_dict()
        )

    def test_metadata_defaults_to_empty_dict_when_none(self) -> None:
        """create_thread() with metadata=None stores {} in the Thread."""
        store, _ = self._make_initialized_store()

        thread = store.create_thread(user_id="user-001", metadata=None)

        assert thread.metadata == {}

    def test_metadata_stored_when_provided(self) -> None:
        """create_thread() stores caller-supplied metadata in the Thread."""
        store, _ = self._make_initialized_store()
        meta = {"title": "My Chat", "agent_id": "agent-42"}

        thread = store.create_thread(user_id="user-001", metadata=meta)

        assert thread.metadata == meta

    def test_raises_storage_connection_error_on_cosmos_http_error(self) -> None:
        """CosmosHttpResponseError during create_item → StorageConnectionError."""
        store, mock_container = self._make_initialized_store()
        mock_container.create_item.side_effect = (
            cosmos_exceptions.CosmosHttpResponseError(
                message="Service unavailable"
            )
        )

        with pytest.raises(StorageConnectionError, match="Failed to create thread"):
            store.create_thread(user_id="user-001")

    def test_storage_connection_error_chains_cosmos_exception(self) -> None:
        """StorageConnectionError is raised 'from' the original CosmosHttpResponseError."""
        store, mock_container = self._make_initialized_store()
        original = cosmos_exceptions.CosmosHttpResponseError(
            message="timeout"
        )
        mock_container.create_item.side_effect = original

        with pytest.raises(StorageConnectionError) as exc_info:
            store.create_thread(user_id="user-001")

        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# append_message()
# ---------------------------------------------------------------------------


class TestCosmosThreadStoreAppendMessage:
    """Tests for CosmosThreadStore.append_message() — FR-002 / T011."""

    def _make_initialized_store(self) -> tuple[CosmosThreadStore, MagicMock]:
        """Return a store with a mocked CosmosClient and container already set."""
        mock_client = MagicMock()
        mock_container = MagicMock()
        with patch("src.thread_store.DefaultAzureCredential"), patch(
            "src.thread_store.CosmosClient", return_value=mock_client
        ):
            store = CosmosThreadStore(
                endpoint=_ENDPOINT,
                database_name=_DATABASE,
                container_name=_CONTAINER,
            )
        store._container = mock_container
        return store, mock_container

    def _make_raw_doc(
        self, thread_id: str = "thread-001", user_id: str = "user-001"
    ) -> dict:
        """Return a minimal Cosmos DB document dict for a thread."""
        return {
            "id": thread_id,
            "user_id": user_id,
            "messages": [],
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
            "metadata": {},
            "_etag": '"etag-v1"',
        }

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_returns_message_object(self) -> None:
        """append_message() returns a Message instance."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()

        result = store.append_message(
            thread_id="thread-001",
            user_id="user-001",
            role="user",
            content="Hello!",
        )

        assert isinstance(result, Message)

    def test_returned_message_has_correct_role_and_content(self) -> None:
        """Returned Message carries the supplied role and content."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()

        msg = store.append_message(
            thread_id="thread-001",
            user_id="user-001",
            role="assistant",
            content="Hi there!",
        )

        assert msg.role == "assistant"
        assert msg.content == "Hi there!"

    def test_returned_message_has_timestamp(self) -> None:
        """Returned Message has a non-empty ISO 8601 timestamp."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()

        msg = store.append_message(
            thread_id="thread-001",
            user_id="user-001",
            role="system",
            content="System prompt.",
        )

        assert msg.timestamp  # non-empty string

    def test_read_item_called_with_correct_args(self) -> None:
        """read_item() is invoked with thread_id and user_id as partition key."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()

        store.append_message(
            thread_id="thread-001",
            user_id="user-001",
            role="user",
            content="Ping",
        )

        mock_container.read_item.assert_called_once_with(
            item="thread-001", partition_key="user-001"
        )

    def test_message_appended_to_messages_array(self) -> None:
        """replace_item() body contains the new message in the messages array."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()

        store.append_message(
            thread_id="thread-001",
            user_id="user-001",
            role="user",
            content="Test message",
        )

        replace_call = mock_container.replace_item.call_args
        body = replace_call.kwargs["body"]
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][0]["content"] == "Test message"
        assert "timestamp" in body["messages"][0]

    def test_updated_at_is_refreshed_in_document(self) -> None:
        """replace_item() body has updated_at newer than the original value."""
        store, mock_container = self._make_initialized_store()
        raw = self._make_raw_doc()
        original_updated_at = raw["updated_at"]
        mock_container.read_item.return_value = raw

        store.append_message(
            thread_id="thread-001",
            user_id="user-001",
            role="user",
            content="Update me",
        )

        replace_call = mock_container.replace_item.call_args
        body = replace_call.kwargs["body"]
        assert body["updated_at"] != original_updated_at

    def test_replace_item_called_with_etag_condition(self) -> None:
        """replace_item() is called with the document ETag and IfNotModified condition."""
        from azure.core import MatchConditions

        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()

        store.append_message(
            thread_id="thread-001",
            user_id="user-001",
            role="user",
            content="Concurrency test",
        )

        replace_call = mock_container.replace_item.call_args
        assert replace_call.kwargs["etag"] == '"etag-v1"'
        assert replace_call.kwargs["match_condition"] == MatchConditions.IfNotModified

    def test_all_valid_roles_accepted(self) -> None:
        """append_message() accepts 'system', 'user', and 'assistant' without error."""
        store, mock_container = self._make_initialized_store()

        for role in ("system", "user", "assistant"):
            mock_container.read_item.return_value = self._make_raw_doc()
            msg = store.append_message(
                thread_id="thread-001",
                user_id="user-001",
                role=role,
                content="Content",
            )
            assert msg.role == role

    # ------------------------------------------------------------------
    # Role validation
    # ------------------------------------------------------------------

    def test_invalid_role_raises_value_error(self) -> None:
        """An unrecognised role raises ValueError before any Cosmos DB call."""
        store, mock_container = self._make_initialized_store()

        with pytest.raises(ValueError, match="Invalid role"):
            store.append_message(
                thread_id="thread-001",
                user_id="user-001",
                role="admin",
                content="Bad role",
            )

        mock_container.read_item.assert_not_called()

    def test_value_error_message_contains_valid_roles(self) -> None:
        """ValueError message lists the accepted role values."""
        store, _ = self._make_initialized_store()

        with pytest.raises(ValueError) as exc_info:
            store.append_message(
                thread_id="thread-001",
                user_id="user-001",
                role="moderator",
                content="Bad role",
            )

        error_msg = str(exc_info.value)
        assert "assistant" in error_msg
        assert "system" in error_msg
        assert "user" in error_msg

    # ------------------------------------------------------------------
    # ThreadNotFoundError
    # ------------------------------------------------------------------

    def test_raises_thread_not_found_when_read_item_missing(self) -> None:
        """CosmosResourceNotFoundError on read → ThreadNotFoundError."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosResourceNotFoundError(
                status_code=404, message="Not found"
            )
        )

        with pytest.raises(ThreadNotFoundError, match="thread-001"):
            store.append_message(
                thread_id="thread-001",
                user_id="user-001",
                role="user",
                content="Hello",
            )

    def test_thread_not_found_chains_original_exception_on_read(self) -> None:
        """ThreadNotFoundError raised 'from' the original CosmosResourceNotFoundError."""
        store, mock_container = self._make_initialized_store()
        original = cosmos_exceptions.CosmosResourceNotFoundError(
            status_code=404, message="Not found"
        )
        mock_container.read_item.side_effect = original

        with pytest.raises(ThreadNotFoundError) as exc_info:
            store.append_message(
                thread_id="thread-001",
                user_id="user-001",
                role="user",
                content="Hello",
            )

        assert exc_info.value.__cause__ is original

    def test_raises_thread_not_found_when_replace_item_missing(self) -> None:
        """CosmosResourceNotFoundError on replace → ThreadNotFoundError."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()
        mock_container.replace_item.side_effect = (
            cosmos_exceptions.CosmosResourceNotFoundError(
                status_code=404, message="Not found"
            )
        )

        with pytest.raises(ThreadNotFoundError, match="thread-001"):
            store.append_message(
                thread_id="thread-001",
                user_id="user-001",
                role="user",
                content="Hello",
            )

    # ------------------------------------------------------------------
    # StorageConnectionError
    # ------------------------------------------------------------------

    def test_raises_storage_connection_error_on_read_http_error(self) -> None:
        """CosmosHttpResponseError on read_item → StorageConnectionError."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosHttpResponseError(message="Service unavailable")
        )

        with pytest.raises(StorageConnectionError, match="thread-001"):
            store.append_message(
                thread_id="thread-001",
                user_id="user-001",
                role="user",
                content="Hello",
            )

    def test_raises_storage_connection_error_on_replace_http_error(self) -> None:
        """CosmosHttpResponseError on replace_item → StorageConnectionError."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()
        mock_container.replace_item.side_effect = (
            cosmos_exceptions.CosmosHttpResponseError(message="Write conflict")
        )

        with pytest.raises(StorageConnectionError):
            store.append_message(
                thread_id="thread-001",
                user_id="user-001",
                role="user",
                content="Hello",
            )

    # ------------------------------------------------------------------
    # ETag optimistic concurrency / retry
    # ------------------------------------------------------------------

    def test_retries_on_etag_conflict_and_succeeds(self) -> None:
        """On a single ETag conflict the method retries and succeeds."""
        store, mock_container = self._make_initialized_store()

        raw_v1 = self._make_raw_doc()
        raw_v1["_etag"] = '"etag-v1"'
        raw_v2 = self._make_raw_doc()
        raw_v2["_etag"] = '"etag-v2"'

        # First read → conflict; second read → success
        mock_container.read_item.side_effect = [raw_v1, raw_v2]
        mock_container.replace_item.side_effect = [
            cosmos_exceptions.CosmosAccessConditionFailedError(),
            MagicMock(),  # success on second attempt
        ]

        result = store.append_message(
            thread_id="thread-001",
            user_id="user-001",
            role="user",
            content="Retry me",
        )

        assert isinstance(result, Message)
        assert mock_container.read_item.call_count == 2
        assert mock_container.replace_item.call_count == 2

    def test_raises_storage_connection_error_after_max_retries(self) -> None:
        """StorageConnectionError raised when all retries are exhausted."""
        store, mock_container = self._make_initialized_store()

        mock_container.read_item.return_value = self._make_raw_doc()
        mock_container.replace_item.side_effect = (
            cosmos_exceptions.CosmosAccessConditionFailedError()
        )

        with pytest.raises(StorageConnectionError, match="ETag conflict"):
            store.append_message(
                thread_id="thread-001",
                user_id="user-001",
                role="user",
                content="Always conflicts",
            )

    def test_read_item_called_max_retries_times_on_persistent_conflict(
        self,
    ) -> None:
        """read_item is called _MAX_ETAG_RETRIES times before giving up."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()
        mock_container.replace_item.side_effect = (
            cosmos_exceptions.CosmosAccessConditionFailedError()
        )

        with pytest.raises(StorageConnectionError):
            store.append_message(
                thread_id="thread-001",
                user_id="user-001",
                role="user",
                content="Always conflicts",
            )

        assert mock_container.read_item.call_count == _MAX_ETAG_RETRIES
        assert mock_container.replace_item.call_count == _MAX_ETAG_RETRIES


# ---------------------------------------------------------------------------
# get_messages  (T012)
# ---------------------------------------------------------------------------


class TestCosmosThreadStoreGetMessages:
    """Tests for CosmosThreadStore.get_messages() — FR-004, FR-007, FR-013 / T012."""

    def _make_initialized_store(self) -> tuple[CosmosThreadStore, MagicMock]:
        """Return a store with a mocked CosmosClient and container already set."""
        mock_client = MagicMock()
        mock_container = MagicMock()
        with patch("src.thread_store.DefaultAzureCredential"), patch(
            "src.thread_store.CosmosClient", return_value=mock_client
        ):
            store = CosmosThreadStore(
                endpoint=_ENDPOINT,
                database_name=_DATABASE,
                container_name=_CONTAINER,
            )
        store._container = mock_container
        return store, mock_container

    def _make_raw_doc(
        self,
        thread_id: str = "thread-001",
        user_id: str = "user-001",
        messages: list[dict] | None = None,
    ) -> dict:
        """Return a minimal Cosmos DB document dict for a thread."""
        return {
            "id": thread_id,
            "user_id": user_id,
            "messages": messages or [],
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
            "metadata": {},
            "_etag": '"etag-v1"',
        }

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_returns_list_of_message_objects(self) -> None:
        """get_messages() returns a list of Message instances."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc(
            messages=[
                {
                    "role": "user",
                    "content": "Hello",
                    "timestamp": "2024-01-01T00:00:01+00:00",
                }
            ]
        )

        result = store.get_messages(thread_id="thread-001", user_id="user-001")

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Message)

    def test_returns_empty_list_for_thread_with_no_messages(self) -> None:
        """get_messages() returns an empty list when the thread has no messages."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc(messages=[])

        result = store.get_messages(thread_id="thread-001", user_id="user-001")

        assert result == []

    def test_returns_all_messages_without_truncation(self) -> None:
        """FR-007: get_messages() returns the complete message list, not a subset."""
        store, mock_container = self._make_initialized_store()
        raw_messages = [
            {
                "role": "user",
                "content": f"Message {i}",
                "timestamp": f"2024-01-01T00:00:0{i}+00:00",
            }
            for i in range(5)
        ]
        mock_container.read_item.return_value = self._make_raw_doc(
            messages=raw_messages
        )

        result = store.get_messages(thread_id="thread-001", user_id="user-001")

        assert len(result) == 5

    def test_messages_sorted_by_timestamp(self) -> None:
        """get_messages() returns messages in ascending timestamp (chronological) order."""
        store, mock_container = self._make_initialized_store()
        # Provide messages stored out of order
        mock_container.read_item.return_value = self._make_raw_doc(
            messages=[
                {
                    "role": "assistant",
                    "content": "Reply",
                    "timestamp": "2024-01-01T00:00:02+00:00",
                },
                {
                    "role": "user",
                    "content": "First",
                    "timestamp": "2024-01-01T00:00:01+00:00",
                },
                {
                    "role": "system",
                    "content": "System prompt",
                    "timestamp": "2024-01-01T00:00:00+00:00",
                },
            ]
        )

        result = store.get_messages(thread_id="thread-001", user_id="user-001")

        assert [m.timestamp for m in result] == [
            "2024-01-01T00:00:00+00:00",
            "2024-01-01T00:00:01+00:00",
            "2024-01-01T00:00:02+00:00",
        ]

    def test_message_fields_preserved(self) -> None:
        """get_messages() preserves role, content, and timestamp of each message."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc(
            messages=[
                {
                    "role": "user",
                    "content": "Hello world",
                    "timestamp": "2024-06-01T12:00:00+00:00",
                }
            ]
        )

        result = store.get_messages(thread_id="thread-001", user_id="user-001")

        assert result[0].role == "user"
        assert result[0].content == "Hello world"
        assert result[0].timestamp == "2024-06-01T12:00:00+00:00"

    def test_uses_point_read_with_correct_args(self) -> None:
        """FR-013: read_item() is called with thread_id and user_id as partition key."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()

        store.get_messages(thread_id="thread-001", user_id="user-001")

        mock_container.read_item.assert_called_once_with(
            item="thread-001", partition_key="user-001"
        )

    # ------------------------------------------------------------------
    # Error paths
    # ------------------------------------------------------------------

    def test_raises_thread_not_found_for_missing_thread(self) -> None:
        """CosmosResourceNotFoundError on read → ThreadNotFoundError."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosResourceNotFoundError(
                status_code=404, message="Not found"
            )
        )

        with pytest.raises(ThreadNotFoundError, match="thread-001"):
            store.get_messages(thread_id="thread-001", user_id="user-001")

    def test_thread_not_found_chains_original_exception(self) -> None:
        """ThreadNotFoundError is raised 'from' the original CosmosResourceNotFoundError."""
        store, mock_container = self._make_initialized_store()
        original = cosmos_exceptions.CosmosResourceNotFoundError(
            status_code=404, message="Not found"
        )
        mock_container.read_item.side_effect = original

        with pytest.raises(ThreadNotFoundError) as exc_info:
            store.get_messages(thread_id="thread-001", user_id="user-001")

        assert exc_info.value.__cause__ is original

    def test_raises_storage_connection_error_on_cosmos_http_error(self) -> None:
        """CosmosHttpResponseError on read_item → StorageConnectionError."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosHttpResponseError(message="Service unavailable")
        )

        with pytest.raises(StorageConnectionError, match="thread-001"):
            store.get_messages(thread_id="thread-001", user_id="user-001")


# ---------------------------------------------------------------------------
# get_thread — T015
# ---------------------------------------------------------------------------


class TestCosmosThreadStoreGetThread:
    """Tests for CosmosThreadStore.get_thread() — FR-003, FR-013 / T015."""

    def _make_initialized_store(self) -> tuple[CosmosThreadStore, MagicMock]:
        """Return a store with a mocked CosmosClient and container already set."""
        mock_client = MagicMock()
        mock_container = MagicMock()
        with patch("src.thread_store.DefaultAzureCredential"), patch(
            "src.thread_store.CosmosClient", return_value=mock_client
        ):
            store = CosmosThreadStore(
                endpoint=_ENDPOINT,
                database_name=_DATABASE,
                container_name=_CONTAINER,
            )
        store._container = mock_container
        return store, mock_container

    def _make_raw_doc(
        self,
        thread_id: str = "thread-001",
        user_id: str = "user-001",
        messages: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Return a minimal Cosmos DB document dict for a thread."""
        return {
            "id": thread_id,
            "user_id": user_id,
            "messages": messages or [],
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:01+00:00",
            "metadata": metadata or {},
            "_etag": '"etag-v1"',
        }

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_returns_thread_object(self) -> None:
        """get_thread() returns a Thread instance on success."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()

        result = store.get_thread(thread_id="thread-001", user_id="user-001")

        assert isinstance(result, Thread)

    def test_thread_id_and_user_id_match_document(self) -> None:
        """get_thread() returns a Thread whose id and user_id match the document."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc(
            thread_id="thread-abc", user_id="user-xyz"
        )

        result = store.get_thread(thread_id="thread-abc", user_id="user-xyz")

        assert result.id == "thread-abc"
        assert result.user_id == "user-xyz"

    def test_thread_timestamps_preserved(self) -> None:
        """get_thread() preserves created_at and updated_at from the document."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()

        result = store.get_thread(thread_id="thread-001", user_id="user-001")

        assert result.created_at == "2024-01-01T00:00:00+00:00"
        assert result.updated_at == "2024-01-01T00:00:01+00:00"

    def test_thread_metadata_preserved(self) -> None:
        """get_thread() preserves arbitrary metadata stored in the document."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc(
            metadata={"title": "My Chat", "agent_id": "agent-42"}
        )

        result = store.get_thread(thread_id="thread-001", user_id="user-001")

        assert result.metadata == {"title": "My Chat", "agent_id": "agent-42"}

    def test_thread_messages_deserialized(self) -> None:
        """get_thread() deserializes embedded messages into Message objects."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc(
            messages=[
                {
                    "role": "user",
                    "content": "Hello",
                    "timestamp": "2024-01-01T00:00:00+00:00",
                },
                {
                    "role": "assistant",
                    "content": "Hi there",
                    "timestamp": "2024-01-01T00:00:01+00:00",
                },
            ]
        )

        result = store.get_thread(thread_id="thread-001", user_id="user-001")

        assert len(result.messages) == 2
        assert result.messages[0].role == "user"
        assert result.messages[0].content == "Hello"
        assert result.messages[1].role == "assistant"
        assert result.messages[1].content == "Hi there"

    def test_thread_with_no_messages_returns_empty_list(self) -> None:
        """get_thread() returns a Thread with an empty messages list when there are none."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc(messages=[])

        result = store.get_thread(thread_id="thread-001", user_id="user-001")

        assert result.messages == []

    def test_uses_point_read_with_thread_id_and_partition_key(self) -> None:
        """FR-013: read_item() is called with thread_id as item and user_id as partition key."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.return_value = self._make_raw_doc()

        store.get_thread(thread_id="thread-001", user_id="user-001")

        mock_container.read_item.assert_called_once_with(
            item="thread-001", partition_key="user-001"
        )

    # ------------------------------------------------------------------
    # Error paths
    # ------------------------------------------------------------------

    def test_raises_thread_not_found_when_document_missing(self) -> None:
        """CosmosResourceNotFoundError → ThreadNotFoundError."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosResourceNotFoundError(
                status_code=404, message="Not found"
            )
        )

        with pytest.raises(ThreadNotFoundError, match="thread-001"):
            store.get_thread(thread_id="thread-001", user_id="user-001")

    def test_thread_not_found_error_mentions_user_id(self) -> None:
        """ThreadNotFoundError message includes both thread_id and user_id."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosResourceNotFoundError(
                status_code=404, message="Not found"
            )
        )

        with pytest.raises(ThreadNotFoundError, match="user-001"):
            store.get_thread(thread_id="thread-001", user_id="user-001")

    def test_thread_not_found_chains_original_exception(self) -> None:
        """ThreadNotFoundError is raised 'from' the original CosmosResourceNotFoundError."""
        store, mock_container = self._make_initialized_store()
        original = cosmos_exceptions.CosmosResourceNotFoundError(
            status_code=404, message="Not found"
        )
        mock_container.read_item.side_effect = original

        with pytest.raises(ThreadNotFoundError) as exc_info:
            store.get_thread(thread_id="thread-001", user_id="user-001")

        assert exc_info.value.__cause__ is original

    def test_raises_storage_connection_error_on_cosmos_http_error(self) -> None:
        """CosmosHttpResponseError on read_item → StorageConnectionError."""
        store, mock_container = self._make_initialized_store()
        mock_container.read_item.side_effect = (
            cosmos_exceptions.CosmosHttpResponseError(message="Service unavailable")
        )

        with pytest.raises(StorageConnectionError, match="thread-001"):
            store.get_thread(thread_id="thread-001", user_id="user-001")

    def test_storage_connection_error_chains_original_exception(self) -> None:
        """StorageConnectionError is raised 'from' the original CosmosHttpResponseError."""
        store, mock_container = self._make_initialized_store()
        original = cosmos_exceptions.CosmosHttpResponseError(
            message="Service unavailable"
        )
        mock_container.read_item.side_effect = original

        with pytest.raises(StorageConnectionError) as exc_info:
            store.get_thread(thread_id="thread-001", user_id="user-001")

        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# list_threads — T016
# ---------------------------------------------------------------------------


class TestCosmosThreadStoreListThreads:
    """Tests for CosmosThreadStore.list_threads() — FR-010 / T016."""

    def _make_initialized_store(self) -> tuple[CosmosThreadStore, MagicMock]:
        """Return a store with a mocked CosmosClient and container already set."""
        mock_client = MagicMock()
        mock_container = MagicMock()
        with patch("src.thread_store.DefaultAzureCredential"), patch(
            "src.thread_store.CosmosClient", return_value=mock_client
        ):
            store = CosmosThreadStore(
                endpoint=_ENDPOINT,
                database_name=_DATABASE,
                container_name=_CONTAINER,
            )
        store._container = mock_container
        return store, mock_container

    def _make_summary_doc(
        self,
        thread_id: str = "thread-001",
        user_id: str = "user-001",
        created_at: str = "2024-01-01T00:00:00+00:00",
        updated_at: str = "2024-01-01T00:00:01+00:00",
        metadata: dict | None = None,
    ) -> dict:
        """Return a Cosmos DB projection dict as returned by the SELECT query."""
        return {
            "id": thread_id,
            "user_id": user_id,
            "created_at": created_at,
            "updated_at": updated_at,
            "metadata": metadata if metadata is not None else {},
        }

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_returns_list_of_thread_summaries(self) -> None:
        """list_threads() returns a list of ThreadSummary instances."""
        store, mock_container = self._make_initialized_store()
        mock_container.query_items.return_value = [self._make_summary_doc()]

        result = store.list_threads(user_id="user-001")

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], ThreadSummary)

    def test_empty_list_when_no_threads_exist(self) -> None:
        """list_threads() returns an empty list when the user has no threads."""
        store, mock_container = self._make_initialized_store()
        mock_container.query_items.return_value = []

        result = store.list_threads(user_id="user-001")

        assert result == []

    def test_multiple_threads_returned(self) -> None:
        """list_threads() returns one ThreadSummary per document."""
        store, mock_container = self._make_initialized_store()
        mock_container.query_items.return_value = [
            self._make_summary_doc(thread_id="thread-001"),
            self._make_summary_doc(thread_id="thread-002"),
            self._make_summary_doc(thread_id="thread-003"),
        ]

        result = store.list_threads(user_id="user-001")

        assert len(result) == 3
        assert [s.id for s in result] == ["thread-001", "thread-002", "thread-003"]

    def test_summary_fields_populated_correctly(self) -> None:
        """Each ThreadSummary has id, user_id, created_at, updated_at populated."""
        store, mock_container = self._make_initialized_store()
        mock_container.query_items.return_value = [
            self._make_summary_doc(
                thread_id="thread-abc",
                user_id="user-xyz",
                created_at="2024-06-01T10:00:00+00:00",
                updated_at="2024-06-01T11:00:00+00:00",
            )
        ]

        result = store.list_threads(user_id="user-xyz")

        summary = result[0]
        assert summary.id == "thread-abc"
        assert summary.user_id == "user-xyz"
        assert summary.created_at == "2024-06-01T10:00:00+00:00"
        assert summary.updated_at == "2024-06-01T11:00:00+00:00"

    def test_metadata_preserved_in_summary(self) -> None:
        """list_threads() preserves arbitrary metadata in each ThreadSummary."""
        store, mock_container = self._make_initialized_store()
        mock_container.query_items.return_value = [
            self._make_summary_doc(metadata={"title": "My Chat", "agent_id": "agent-42"})
        ]

        result = store.list_threads(user_id="user-001")

        assert result[0].metadata == {"title": "My Chat", "agent_id": "agent-42"}

    def test_missing_metadata_defaults_to_empty_dict(self) -> None:
        """list_threads() defaults metadata to {} when the field is absent."""
        store, mock_container = self._make_initialized_store()
        doc = self._make_summary_doc()
        doc.pop("metadata")
        mock_container.query_items.return_value = [doc]

        result = store.list_threads(user_id="user-001")

        assert result[0].metadata == {}

    def test_query_uses_partition_key(self) -> None:
        """FR-010: query_items() is called with user_id as partition_key to avoid cross-partition queries."""
        store, mock_container = self._make_initialized_store()
        mock_container.query_items.return_value = []

        store.list_threads(user_id="user-001")

        _, kwargs = mock_container.query_items.call_args
        assert kwargs.get("partition_key") == "user-001"

    def test_query_filters_by_user_id_parameter(self) -> None:
        """The SQL query passes user_id as a named parameter @user_id."""
        store, mock_container = self._make_initialized_store()
        mock_container.query_items.return_value = []

        store.list_threads(user_id="user-001")

        _, kwargs = mock_container.query_items.call_args
        parameters = kwargs.get("parameters", [])
        user_id_param = next(
            (p for p in parameters if p["name"] == "@user_id"), None
        )
        assert user_id_param is not None
        assert user_id_param["value"] == "user-001"

    def test_query_selects_only_summary_fields(self) -> None:
        """The SQL query projects only summary fields and does not include messages."""
        store, mock_container = self._make_initialized_store()
        mock_container.query_items.return_value = []

        store.list_threads(user_id="user-001")

        _, kwargs = mock_container.query_items.call_args
        query: str = kwargs.get("query", "")
        assert "messages" not in query.lower()
        assert "c.id" in query
        assert "c.user_id" in query
        assert "c.created_at" in query
        assert "c.updated_at" in query
        assert "c.metadata" in query

    # ------------------------------------------------------------------
    # Error paths
    # ------------------------------------------------------------------

    def test_raises_storage_connection_error_on_cosmos_http_error(self) -> None:
        """CosmosHttpResponseError on query_items → StorageConnectionError."""
        store, mock_container = self._make_initialized_store()
        mock_container.query_items.side_effect = (
            cosmos_exceptions.CosmosHttpResponseError(message="Service unavailable")
        )

        with pytest.raises(StorageConnectionError, match="user-001"):
            store.list_threads(user_id="user-001")

    def test_storage_connection_error_chains_original_exception(self) -> None:
        """StorageConnectionError is raised 'from' the original CosmosHttpResponseError."""
        store, mock_container = self._make_initialized_store()
        original = cosmos_exceptions.CosmosHttpResponseError(
            message="Service unavailable"
        )
        mock_container.query_items.side_effect = original

        with pytest.raises(StorageConnectionError) as exc_info:
            store.list_threads(user_id="user-001")

        assert exc_info.value.__cause__ is original


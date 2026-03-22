"""Unit tests for CosmosThreadStore.__init__(), initialize(), and create_thread() — T008/T009."""

from unittest.mock import MagicMock, patch

import pytest
from azure.cosmos import PartitionKey, exceptions as cosmos_exceptions

from src.exceptions import StorageConnectionError
from src.models import Thread
from src.thread_store import CosmosThreadStore


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

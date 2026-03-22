"""CosmosThreadStore — Azure Cosmos DB thread storage for Foundry Agent."""

from datetime import datetime, timezone
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.core import MatchConditions
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from src.exceptions import (
    StorageConnectionError,
    ThreadNotFoundError,
)
from src.models import Message, Thread, ThreadSummary

_VALID_ROLES = {"system", "user", "assistant"}
_MAX_ETAG_RETRIES = 3


def _utc_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


class CosmosThreadStore:
    """Thread storage backed by Azure Cosmos DB for NoSQL.

    All public methods require a ``user_id`` argument to enforce per-user
    data isolation via Cosmos DB partition keys (FR-013).

    Example::

        store = CosmosThreadStore(
            endpoint="https://my-account.documents.azure.com:443/",
            database_name="thread_storage",
            container_name="threads",
        )
        store.initialize()
        thread = store.create_thread(user_id="user-001")
    """

    def __init__(
        self,
        endpoint: str,
        database_name: str,
        container_name: str,
        credential: TokenCredential | None = None,
    ) -> None:
        """Initialise CosmosThreadStore.

        Args:
            endpoint: Cosmos DB account endpoint URL.
            database_name: Target database name.
            container_name: Target container name.
            credential: Azure TokenCredential instance.
                Defaults to DefaultAzureCredential when not provided (FR-008).
        """
        self._endpoint = endpoint
        self._database_name = database_name
        self._container_name = container_name
        self._credential = credential or DefaultAzureCredential()
        self._client: CosmosClient = CosmosClient(
            url=self._endpoint, credential=self._credential
        )
        self._container = None  # lazily set by initialize()

    def initialize(self) -> None:
        """Create the database and container if they do not exist (FR-011).

        Sets the partition key to ``/user_id``.

        Raises:
            StorageConnectionError: Cannot connect to Cosmos DB.
        """
        try:
            database = self._client.create_database_if_not_exists(
                id=self._database_name
            )
            self._container = database.create_container_if_not_exists(
                id=self._container_name,
                partition_key=PartitionKey(path="/user_id"),
            )
        except exceptions.CosmosHttpResponseError as exc:
            raise StorageConnectionError(
                f"Failed to initialise Cosmos DB storage: {exc.message}"
            ) from exc
        except Exception as exc:
            raise StorageConnectionError(
                f"Unexpected error connecting to Cosmos DB: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # US1: Create thread
    # ------------------------------------------------------------------

    def create_thread(
        self,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Thread:
        """Create a new conversation thread in Cosmos DB (FR-001).

        Args:
            user_id: Owner's user identifier.
            metadata: Optional key-value metadata (e.g. agent_id, title).

        Returns:
            The newly created Thread object.

        Raises:
            StorageConnectionError: Cosmos DB operation failed.
        """
        thread = Thread(user_id=user_id, metadata=metadata or {})
        try:
            self._container.create_item(body=thread.to_dict())
        except exceptions.CosmosHttpResponseError as exc:
            raise StorageConnectionError(
                f"Failed to create thread: {exc.message}"
            ) from exc
        return thread

    # ------------------------------------------------------------------
    # US2: Append message & get messages
    # ------------------------------------------------------------------

    def append_message(
        self,
        thread_id: str,
        user_id: str,
        role: str,
        content: str,
    ) -> Message:
        """Append a message to the specified thread (FR-002).

        Uses optimistic concurrency (ETag) with up to 3 retries on conflict.

        Args:
            thread_id: Thread identifier.
            user_id: Owner's user identifier (partition key).
            role: Message role — must be "system", "user", or "assistant".
            content: Message text content.

        Returns:
            The newly appended Message object.

        Raises:
            ValueError: ``role`` is not one of the valid values.
            ThreadNotFoundError: Thread does not exist or does not belong
                to ``user_id``.
            StorageConnectionError: Cosmos DB operation failed.
        """
        if role not in _VALID_ROLES:
            raise ValueError(
                f"Invalid role '{role}'. Must be one of: "
                + ", ".join(sorted(_VALID_ROLES))
            )

        message = Message(role=role, content=content)

        for attempt in range(_MAX_ETAG_RETRIES):
            try:
                raw = self._container.read_item(
                    item=thread_id, partition_key=user_id
                )
            except exceptions.CosmosResourceNotFoundError as exc:
                raise ThreadNotFoundError(
                    f"Thread '{thread_id}' not found for user '{user_id}'."
                ) from exc
            except exceptions.CosmosHttpResponseError as exc:
                raise StorageConnectionError(
                    f"Failed to read thread '{thread_id}': {exc.message}"
                ) from exc

            raw["messages"].append(
                {
                    "role": message.role,
                    "content": message.content,
                    "timestamp": message.timestamp,
                }
            )
            raw["updated_at"] = _utc_now()

            try:
                self._container.replace_item(
                    item=thread_id,
                    body=raw,
                    etag=raw["_etag"],
                    match_condition=MatchConditions.IfNotModified,
                )
                return message
            except exceptions.CosmosAccessConditionFailedError:
                if attempt == _MAX_ETAG_RETRIES - 1:
                    raise StorageConnectionError(
                        f"ETag conflict on thread '{thread_id}' after "
                        f"{_MAX_ETAG_RETRIES} retries."
                    )
                # Retry with fresh read
            except exceptions.CosmosResourceNotFoundError as exc:
                raise ThreadNotFoundError(
                    f"Thread '{thread_id}' not found for user '{user_id}'."
                ) from exc
            except exceptions.CosmosHttpResponseError as exc:
                raise StorageConnectionError(
                    f"Failed to update thread '{thread_id}': {exc.message}"
                ) from exc

        # Should not reach here, but satisfy type checker
        raise StorageConnectionError(  # pragma: no cover
            f"Failed to append message to thread '{thread_id}'."
        )

    def get_messages(
        self,
        thread_id: str,
        user_id: str,
    ) -> list[Message]:
        """Return the complete message list for a thread (FR-004, FR-007).

        Args:
            thread_id: Thread identifier.
            user_id: Owner's user identifier.

        Returns:
            Full list of messages in chronological order.

        Raises:
            ThreadNotFoundError: Thread does not exist or does not belong
                to ``user_id``.
            StorageConnectionError: Cosmos DB operation failed.
        """
        thread = self.get_thread(thread_id, user_id)
        return sorted(thread.messages, key=lambda m: m.timestamp)

    # ------------------------------------------------------------------
    # US3: Get thread & list threads
    # ------------------------------------------------------------------

    def get_thread(
        self,
        thread_id: str,
        user_id: str,
    ) -> Thread:
        """Retrieve a complete thread by ID (FR-003, FR-013).

        Args:
            thread_id: Thread identifier.
            user_id: Owner's user identifier (partition key and ownership check).

        Returns:
            Full Thread object including all messages and metadata.

        Raises:
            ThreadNotFoundError: Thread does not exist or does not belong
                to ``user_id``.
            StorageConnectionError: Cosmos DB operation failed.
        """
        try:
            raw = self._container.read_item(
                item=thread_id, partition_key=user_id
            )
        except exceptions.CosmosResourceNotFoundError as exc:
            raise ThreadNotFoundError(
                f"Thread '{thread_id}' not found for user '{user_id}'."
            ) from exc
        except exceptions.CosmosHttpResponseError as exc:
            raise StorageConnectionError(
                f"Failed to read thread '{thread_id}': {exc.message}"
            ) from exc
        return Thread.from_dict(raw)

    def list_threads(
        self,
        user_id: str,
    ) -> list[ThreadSummary]:
        """List all thread summaries for a user (FR-010).

        Returns lightweight summaries without the messages array to reduce
        data transfer (charter principle II).

        Args:
            user_id: Owner's user identifier.

        Returns:
            List of ThreadSummary objects ordered by Cosmos DB default.

        Raises:
            StorageConnectionError: Cosmos DB operation failed.
        """
        query = (
            "SELECT c.id, c.user_id, c.created_at, c.updated_at, c.metadata "
            "FROM c WHERE c.user_id = @user_id"
        )
        parameters: list[dict[str, Any]] = [
            {"name": "@user_id", "value": user_id}
        ]
        try:
            items = list(
                self._container.query_items(
                    query=query,
                    parameters=parameters,
                    partition_key=user_id,
                )
            )
        except exceptions.CosmosHttpResponseError as exc:
            raise StorageConnectionError(
                f"Failed to list threads for user '{user_id}': {exc.message}"
            ) from exc
        return [
            ThreadSummary(
                id=item["id"],
                user_id=item["user_id"],
                created_at=item["created_at"],
                updated_at=item["updated_at"],
                metadata=item.get("metadata", {}),
            )
            for item in items
        ]

    # ------------------------------------------------------------------
    # US4: Delete thread
    # ------------------------------------------------------------------

    def delete_thread(
        self,
        thread_id: str,
        user_id: str,
    ) -> None:
        """Permanently delete a thread from Cosmos DB (FR-005, FR-013).

        Args:
            thread_id: Thread identifier.
            user_id: Owner's user identifier (partition key).

        Raises:
            ThreadNotFoundError: Thread does not exist or does not belong
                to ``user_id``.
            StorageConnectionError: Cosmos DB operation failed.
        """
        try:
            self._container.delete_item(
                item=thread_id, partition_key=user_id
            )
        except exceptions.CosmosResourceNotFoundError as exc:
            raise ThreadNotFoundError(
                f"Thread '{thread_id}' not found for user '{user_id}'."
            ) from exc
        except exceptions.CosmosHttpResponseError as exc:
            raise StorageConnectionError(
                f"Failed to delete thread '{thread_id}': {exc.message}"
            ) from exc

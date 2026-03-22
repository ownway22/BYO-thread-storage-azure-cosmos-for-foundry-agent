"""Data models for BYO Thread Storage."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _utc_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Message:
    """A single conversation message embedded in a Thread.

    Attributes:
        role: Message sender role — "system", "user", or "assistant".
        content: Text content of the message.
        timestamp: UTC ISO 8601 timestamp of when the message was created.
    """

    role: str
    content: str
    timestamp: str = field(default_factory=_utc_now)


@dataclass
class Thread:
    """A conversation thread stored in Cosmos DB.

    Attributes:
        user_id: Owner's user identifier (partition key).
        id: Unique thread identifier (UUID v4).
        messages: Ordered list of conversation messages.
        created_at: UTC ISO 8601 creation timestamp.
        updated_at: UTC ISO 8601 last-modified timestamp.
        metadata: Optional key-value metadata (e.g. agent_id, title).
    """

    user_id: str
    id: str = field(default_factory=lambda: str(uuid4()))
    messages: list[Message] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the Thread to a Cosmos DB-compatible dictionary.

        Returns:
            Dictionary representation of the thread.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                }
                for msg in self.messages
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Thread":
        """Deserialize a Thread from a Cosmos DB document dictionary.

        Args:
            data: Raw dictionary from Cosmos DB.

        Returns:
            Thread dataclass instance.
        """
        messages = [
            Message(
                role=msg["role"],
                content=msg["content"],
                timestamp=msg["timestamp"],
            )
            for msg in data.get("messages", [])
        ]
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            messages=messages,
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            metadata=data.get("metadata", {}),
        )


@dataclass
class ThreadSummary:
    """Lightweight thread summary returned by list_threads (no messages).

    Attributes:
        id: Thread identifier.
        user_id: Owner's user identifier.
        created_at: UTC ISO 8601 creation timestamp.
        updated_at: UTC ISO 8601 last-modified timestamp.
        metadata: Optional key-value metadata.
    """

    id: str
    user_id: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

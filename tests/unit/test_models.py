"""Unit tests for src/models.py — Thread, Message, ThreadSummary dataclasses."""

from datetime import datetime, timezone

import pytest

from src.models import Message, Thread, ThreadSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_utc_iso8601(value: str) -> bool:
    """Return True if *value* is a valid UTC ISO 8601 datetime string."""
    try:
        dt = datetime.fromisoformat(value)
        return dt.tzinfo is not None
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class TestMessage:
    """Tests for the Message dataclass."""

    def test_required_fields_stored(self) -> None:
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_timestamp_defaults_to_utc_iso8601(self) -> None:
        msg = Message(role="assistant", content="Hi")
        assert _is_utc_iso8601(msg.timestamp)

    def test_timestamp_can_be_overridden(self) -> None:
        ts = "2026-01-01T00:00:00+00:00"
        msg = Message(role="system", content="Sys prompt", timestamp=ts)
        assert msg.timestamp == ts

    def test_all_roles_accepted(self) -> None:
        for role in ("system", "user", "assistant"):
            msg = Message(role=role, content="test")
            assert msg.role == role


# ---------------------------------------------------------------------------
# Thread
# ---------------------------------------------------------------------------


class TestThread:
    """Tests for the Thread dataclass."""

    def test_user_id_is_required(self) -> None:
        t = Thread(user_id="user-abc")
        assert t.user_id == "user-abc"

    def test_id_defaults_to_uuid(self) -> None:
        import re

        t = Thread(user_id="u")
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            re.IGNORECASE,
        )
        assert uuid_pattern.match(t.id), f"id {t.id!r} is not a UUID v4"

    def test_id_is_unique_per_instance(self) -> None:
        t1 = Thread(user_id="u")
        t2 = Thread(user_id="u")
        assert t1.id != t2.id

    def test_messages_defaults_to_empty_list(self) -> None:
        t = Thread(user_id="u")
        assert t.messages == []

    def test_metadata_defaults_to_empty_dict(self) -> None:
        t = Thread(user_id="u")
        assert t.metadata == {}

    def test_created_at_defaults_to_utc_iso8601(self) -> None:
        t = Thread(user_id="u")
        assert _is_utc_iso8601(t.created_at)

    def test_updated_at_defaults_to_utc_iso8601(self) -> None:
        t = Thread(user_id="u")
        assert _is_utc_iso8601(t.updated_at)

    def test_messages_list_is_not_shared_across_instances(self) -> None:
        t1 = Thread(user_id="u")
        t2 = Thread(user_id="u")
        t1.messages.append(Message(role="user", content="hi"))
        assert t2.messages == []

    # ------------------------------------------------------------------
    # to_dict
    # ------------------------------------------------------------------

    def test_to_dict_contains_all_keys(self) -> None:
        t = Thread(user_id="u")
        d = t.to_dict()
        assert set(d.keys()) == {"id", "user_id", "messages", "created_at", "updated_at", "metadata"}

    def test_to_dict_messages_are_plain_dicts(self) -> None:
        msg = Message(role="user", content="Hello", timestamp="2026-01-01T00:00:00+00:00")
        t = Thread(user_id="u", messages=[msg])
        d = t.to_dict()
        assert len(d["messages"]) == 1
        assert d["messages"][0] == {
            "role": "user",
            "content": "Hello",
            "timestamp": "2026-01-01T00:00:00+00:00",
        }

    def test_to_dict_empty_messages(self) -> None:
        t = Thread(user_id="u")
        assert t.to_dict()["messages"] == []

    def test_to_dict_metadata_preserved(self) -> None:
        t = Thread(user_id="u", metadata={"title": "Trip planning"})
        assert t.to_dict()["metadata"] == {"title": "Trip planning"}

    # ------------------------------------------------------------------
    # from_dict
    # ------------------------------------------------------------------

    def test_from_dict_round_trip(self) -> None:
        original = Thread(
            user_id="user-123",
            messages=[
                Message(role="user", content="Hi", timestamp="2026-01-01T00:00:00+00:00"),
                Message(role="assistant", content="Hello!", timestamp="2026-01-01T00:00:01+00:00"),
            ],
            metadata={"agent_id": "agent-001"},
        )
        restored = Thread.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.user_id == original.user_id
        assert restored.created_at == original.created_at
        assert restored.updated_at == original.updated_at
        assert restored.metadata == original.metadata
        assert len(restored.messages) == 2
        assert restored.messages[0].role == "user"
        assert restored.messages[0].content == "Hi"
        assert restored.messages[1].role == "assistant"

    def test_from_dict_missing_messages_defaults_to_empty(self) -> None:
        data = {
            "id": "abc",
            "user_id": "u",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        t = Thread.from_dict(data)
        assert t.messages == []

    def test_from_dict_missing_metadata_defaults_to_empty(self) -> None:
        data = {
            "id": "abc",
            "user_id": "u",
            "messages": [],
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        t = Thread.from_dict(data)
        assert t.metadata == {}

    def test_from_dict_restores_message_objects(self) -> None:
        data = {
            "id": "abc",
            "user_id": "u",
            "messages": [
                {"role": "user", "content": "test", "timestamp": "2026-01-01T00:00:00+00:00"}
            ],
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        t = Thread.from_dict(data)
        assert isinstance(t.messages[0], Message)


# ---------------------------------------------------------------------------
# ThreadSummary
# ---------------------------------------------------------------------------


class TestThreadSummary:
    """Tests for the ThreadSummary dataclass."""

    def test_required_fields_stored(self) -> None:
        ts = ThreadSummary(
            id="thread-1",
            user_id="user-abc",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:01+00:00",
        )
        assert ts.id == "thread-1"
        assert ts.user_id == "user-abc"
        assert ts.created_at == "2026-01-01T00:00:00+00:00"
        assert ts.updated_at == "2026-01-01T00:00:01+00:00"

    def test_metadata_defaults_to_empty_dict(self) -> None:
        ts = ThreadSummary(
            id="x",
            user_id="u",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        assert ts.metadata == {}

    def test_metadata_can_be_provided(self) -> None:
        ts = ThreadSummary(
            id="x",
            user_id="u",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            metadata={"title": "My thread"},
        )
        assert ts.metadata == {"title": "My thread"}

    def test_metadata_not_shared_across_instances(self) -> None:
        ts1 = ThreadSummary(
            id="x", user_id="u", created_at="t", updated_at="t"
        )
        ts2 = ThreadSummary(
            id="y", user_id="u", created_at="t", updated_at="t"
        )
        ts1.metadata["key"] = "value"
        assert "key" not in ts2.metadata

    def test_no_messages_field(self) -> None:
        ts = ThreadSummary(
            id="x", user_id="u", created_at="t", updated_at="t"
        )
        assert not hasattr(ts, "messages"), "ThreadSummary must not have a messages field"

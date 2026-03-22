"""Unit tests for src/exceptions.py — custom exception hierarchy."""

import pytest

from src.exceptions import (
    AccessDeniedError,
    StorageConnectionError,
    ThreadNotFoundError,
    ThreadStorageError,
)


# ---------------------------------------------------------------------------
# ThreadStorageError — base class
# ---------------------------------------------------------------------------


class TestThreadStorageError:
    """Tests for the ThreadStorageError base exception."""

    def test_is_exception_subclass(self) -> None:
        assert issubclass(ThreadStorageError, Exception)

    def test_can_be_raised_without_message(self) -> None:
        with pytest.raises(ThreadStorageError):
            raise ThreadStorageError()

    def test_can_be_raised_with_message(self) -> None:
        with pytest.raises(ThreadStorageError, match="storage error"):
            raise ThreadStorageError("storage error")

    def test_message_is_preserved(self) -> None:
        exc = ThreadStorageError("base error message")
        assert str(exc) == "base error message"


# ---------------------------------------------------------------------------
# ThreadNotFoundError
# ---------------------------------------------------------------------------


class TestThreadNotFoundError:
    """Tests for the ThreadNotFoundError exception."""

    def test_is_thread_storage_error_subclass(self) -> None:
        assert issubclass(ThreadNotFoundError, ThreadStorageError)

    def test_is_exception_subclass(self) -> None:
        assert issubclass(ThreadNotFoundError, Exception)

    def test_can_be_raised_without_message(self) -> None:
        with pytest.raises(ThreadNotFoundError):
            raise ThreadNotFoundError()

    def test_can_be_raised_with_message(self) -> None:
        with pytest.raises(ThreadNotFoundError, match="thread-abc not found"):
            raise ThreadNotFoundError("thread-abc not found")

    def test_message_is_preserved(self) -> None:
        exc = ThreadNotFoundError("thread-123 not found")
        assert str(exc) == "thread-123 not found"

    def test_caught_as_thread_storage_error(self) -> None:
        with pytest.raises(ThreadStorageError):
            raise ThreadNotFoundError("not found")


# ---------------------------------------------------------------------------
# AccessDeniedError
# ---------------------------------------------------------------------------


class TestAccessDeniedError:
    """Tests for the AccessDeniedError exception."""

    def test_is_thread_storage_error_subclass(self) -> None:
        assert issubclass(AccessDeniedError, ThreadStorageError)

    def test_is_exception_subclass(self) -> None:
        assert issubclass(AccessDeniedError, Exception)

    def test_can_be_raised_without_message(self) -> None:
        with pytest.raises(AccessDeniedError):
            raise AccessDeniedError()

    def test_can_be_raised_with_message(self) -> None:
        with pytest.raises(AccessDeniedError, match="access denied"):
            raise AccessDeniedError("access denied")

    def test_message_is_preserved(self) -> None:
        exc = AccessDeniedError("user has no permission")
        assert str(exc) == "user has no permission"

    def test_caught_as_thread_storage_error(self) -> None:
        with pytest.raises(ThreadStorageError):
            raise AccessDeniedError("denied")


# ---------------------------------------------------------------------------
# StorageConnectionError
# ---------------------------------------------------------------------------


class TestStorageConnectionError:
    """Tests for the StorageConnectionError exception."""

    def test_is_thread_storage_error_subclass(self) -> None:
        assert issubclass(StorageConnectionError, ThreadStorageError)

    def test_is_exception_subclass(self) -> None:
        assert issubclass(StorageConnectionError, Exception)

    def test_can_be_raised_without_message(self) -> None:
        with pytest.raises(StorageConnectionError):
            raise StorageConnectionError()

    def test_can_be_raised_with_message(self) -> None:
        with pytest.raises(StorageConnectionError, match="connection failed"):
            raise StorageConnectionError("connection failed")

    def test_message_is_preserved(self) -> None:
        exc = StorageConnectionError("unable to reach Cosmos DB")
        assert str(exc) == "unable to reach Cosmos DB"

    def test_caught_as_thread_storage_error(self) -> None:
        with pytest.raises(ThreadStorageError):
            raise StorageConnectionError("connection error")


# ---------------------------------------------------------------------------
# Cross-class: all four are distinct types
# ---------------------------------------------------------------------------


class TestExceptionDistinctness:
    """Verify the four exception types are mutually distinct."""

    def test_thread_not_found_is_not_access_denied(self) -> None:
        assert not issubclass(ThreadNotFoundError, AccessDeniedError)

    def test_thread_not_found_is_not_storage_connection(self) -> None:
        assert not issubclass(ThreadNotFoundError, StorageConnectionError)

    def test_access_denied_is_not_storage_connection(self) -> None:
        assert not issubclass(AccessDeniedError, StorageConnectionError)

    def test_specific_exception_not_caught_by_sibling(self) -> None:
        """StorageConnectionError should not be caught by ThreadNotFoundError."""
        with pytest.raises(StorageConnectionError):
            try:
                raise StorageConnectionError("conn error")
            except ThreadNotFoundError:
                pass  # Must not be caught here

"""Custom exception hierarchy for BYO Thread Storage."""


class ThreadStorageError(Exception):
    """Base exception for all thread storage errors."""


class ThreadNotFoundError(ThreadStorageError):
    """Raised when a thread does not exist or does not belong to the user.

    Maps to Cosmos DB HTTP 404 responses.
    """


class AccessDeniedError(ThreadStorageError):
    """Raised when a user is not authorised to access a resource.

    Reserved for future RBAC expansion; not currently triggered.
    """


class StorageConnectionError(ThreadStorageError):
    """Raised when a connection to Cosmos DB cannot be established.

    Maps to network errors and Cosmos DB service unavailability (FR-009).
    """

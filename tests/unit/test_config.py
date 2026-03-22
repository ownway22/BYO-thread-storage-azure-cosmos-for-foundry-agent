"""Unit tests for src/config.py — ThreadStoreConfig dataclass."""

import os

import pytest

from src.config import ThreadStoreConfig


# ---------------------------------------------------------------------------
# Direct construction
# ---------------------------------------------------------------------------


class TestThreadStoreConfigConstruction:
    """Tests for direct instantiation of ThreadStoreConfig."""

    def test_required_field_cosmos_endpoint_stored(self) -> None:
        cfg = ThreadStoreConfig(cosmos_endpoint="https://example.documents.azure.com:443/")
        assert cfg.cosmos_endpoint == "https://example.documents.azure.com:443/"

    def test_cosmos_database_name_defaults_to_thread_storage(self) -> None:
        cfg = ThreadStoreConfig(cosmos_endpoint="https://example.documents.azure.com:443/")
        assert cfg.cosmos_database_name == "thread_storage"

    def test_cosmos_container_name_defaults_to_threads(self) -> None:
        cfg = ThreadStoreConfig(cosmos_endpoint="https://example.documents.azure.com:443/")
        assert cfg.cosmos_container_name == "threads"

    def test_azure_ai_project_endpoint_defaults_to_none(self) -> None:
        cfg = ThreadStoreConfig(cosmos_endpoint="https://example.documents.azure.com:443/")
        assert cfg.azure_ai_project_endpoint is None

    def test_all_fields_can_be_overridden(self) -> None:
        cfg = ThreadStoreConfig(
            cosmos_endpoint="https://myaccount.documents.azure.com:443/",
            cosmos_database_name="my_db",
            cosmos_container_name="my_container",
            azure_ai_project_endpoint="https://myproject.api.azureml.ms",
        )
        assert cfg.cosmos_endpoint == "https://myaccount.documents.azure.com:443/"
        assert cfg.cosmos_database_name == "my_db"
        assert cfg.cosmos_container_name == "my_container"
        assert cfg.azure_ai_project_endpoint == "https://myproject.api.azureml.ms"

    def test_cosmos_endpoint_is_required(self) -> None:
        """Omitting cosmos_endpoint should raise TypeError (missing argument)."""
        with pytest.raises(TypeError):
            ThreadStoreConfig()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# from_env — happy path
# ---------------------------------------------------------------------------


class TestThreadStoreConfigFromEnv:
    """Tests for ThreadStoreConfig.from_env() classmethod."""

    def test_from_env_loads_cosmos_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://env.documents.azure.com:443/")
        monkeypatch.delenv("COSMOS_DATABASE_NAME", raising=False)
        monkeypatch.delenv("COSMOS_CONTAINER_NAME", raising=False)
        monkeypatch.delenv("AZURE_AI_PROJECT_ENDPOINT", raising=False)

        cfg = ThreadStoreConfig.from_env()

        assert cfg.cosmos_endpoint == "https://env.documents.azure.com:443/"

    def test_from_env_uses_default_database_name_when_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://env.documents.azure.com:443/")
        monkeypatch.delenv("COSMOS_DATABASE_NAME", raising=False)

        cfg = ThreadStoreConfig.from_env()

        assert cfg.cosmos_database_name == "thread_storage"

    def test_from_env_uses_default_container_name_when_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://env.documents.azure.com:443/")
        monkeypatch.delenv("COSMOS_CONTAINER_NAME", raising=False)

        cfg = ThreadStoreConfig.from_env()

        assert cfg.cosmos_container_name == "threads"

    def test_from_env_loads_optional_database_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://env.documents.azure.com:443/")
        monkeypatch.setenv("COSMOS_DATABASE_NAME", "custom_db")

        cfg = ThreadStoreConfig.from_env()

        assert cfg.cosmos_database_name == "custom_db"

    def test_from_env_loads_optional_container_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://env.documents.azure.com:443/")
        monkeypatch.setenv("COSMOS_CONTAINER_NAME", "custom_container")

        cfg = ThreadStoreConfig.from_env()

        assert cfg.cosmos_container_name == "custom_container"

    def test_from_env_loads_azure_ai_project_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://env.documents.azure.com:443/")
        monkeypatch.setenv(
            "AZURE_AI_PROJECT_ENDPOINT", "https://myproject.api.azureml.ms"
        )

        cfg = ThreadStoreConfig.from_env()

        assert cfg.azure_ai_project_endpoint == "https://myproject.api.azureml.ms"

    def test_from_env_azure_ai_project_endpoint_none_when_not_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://env.documents.azure.com:443/")
        monkeypatch.delenv("AZURE_AI_PROJECT_ENDPOINT", raising=False)

        cfg = ThreadStoreConfig.from_env()

        assert cfg.azure_ai_project_endpoint is None

    def test_from_env_returns_thread_store_config_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COSMOS_ENDPOINT", "https://env.documents.azure.com:443/")

        cfg = ThreadStoreConfig.from_env()

        assert isinstance(cfg, ThreadStoreConfig)


# ---------------------------------------------------------------------------
# from_env — missing required variable
# ---------------------------------------------------------------------------


class TestThreadStoreConfigFromEnvMissingRequired:
    """Tests that from_env() raises ValueError for missing required env vars."""

    def test_from_env_raises_value_error_when_cosmos_endpoint_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("COSMOS_ENDPOINT", raising=False)

        with pytest.raises(ValueError, match="COSMOS_ENDPOINT"):
            ThreadStoreConfig.from_env()

    def test_from_env_raises_value_error_when_cosmos_endpoint_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COSMOS_ENDPOINT", "")

        with pytest.raises(ValueError, match="COSMOS_ENDPOINT"):
            ThreadStoreConfig.from_env()

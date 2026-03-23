"""Configuration dataclass for BYO Thread Storage."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class ThreadStoreConfig:
    """Storage layer configuration loaded from environment variables (FR-012).

    Attributes:
        cosmos_endpoint: Cosmos DB account endpoint URL (required).
        cosmos_database_name: Database name (default: "thread_storage").
        cosmos_container_name: Container name (default: "threads").
        azure_ai_project_endpoint: Foundry project endpoint (optional,
            required only when using agent_integration).
        foundry_agent_name: Foundry application/agent name (optional,
            required only when using agent_integration, e.g. "RAI-agent").
        foundry_model_name: The agent's underlying model name (optional,
            required only when using agent_integration, e.g. "gpt-4.1-mini").
    """

    cosmos_endpoint: str
    cosmos_database_name: str = "thread_storage"
    cosmos_container_name: str = "threads"
    azure_ai_project_endpoint: str | None = None
    foundry_agent_name: str | None = None
    foundry_model_name: str | None = None

    @classmethod
    def from_env(cls) -> "ThreadStoreConfig":
        """Load configuration from environment variables via python-dotenv.

        Reads a .env file if present, then falls back to process environment.

        Returns:
            ThreadStoreConfig populated from environment variables.

        Raises:
            ValueError: If the required COSMOS_ENDPOINT variable is not set.
        """
        load_dotenv()

        endpoint = os.getenv("COSMOS_ENDPOINT")
        if not endpoint:
            raise ValueError(
                "COSMOS_ENDPOINT environment variable is required but not set. "
                "Copy .env.sample to .env and fill in your Cosmos DB endpoint."
            )

        return cls(
            cosmos_endpoint=endpoint,
            cosmos_database_name=os.getenv("COSMOS_DATABASE_NAME", "thread_storage"),
            cosmos_container_name=os.getenv("COSMOS_CONTAINER_NAME", "threads"),
            azure_ai_project_endpoint=os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
            foundry_agent_name=os.getenv("FOUNDRY_AGENT_NAME"),
            foundry_model_name=os.getenv("FOUNDRY_MODEL_NAME"),
        )

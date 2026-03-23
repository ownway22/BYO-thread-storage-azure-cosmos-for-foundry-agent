"""Foundry Agent integration for BYO Thread Storage (FR-006).

Uses the OpenAI Responses API to communicate with Foundry-hosted agents.
The base URL targets the agent application endpoint directly:
``{project_endpoint}/applications/{agent_name}/protocols/openai``
"""

import os

import openai
from azure.identity import DefaultAzureCredential

from src.thread_store import CosmosThreadStore

_AZURE_ML_SCOPE = "https://ml.azure.com/.default"


def run_agent_conversation(
    store: CosmosThreadStore,
    user_id: str,
    user_message: str,
    thread_id: str | None = None,
    agent_name: str | None = None,
    model_name: str | None = None,
) -> tuple[str, str]:
    """Run one turn of a Foundry Agent conversation with persistent history.

    Stores every message in Cosmos DB so the full conversation context is
    available for subsequent turns (FR-006, FR-007).

    Uses the OpenAI Responses API to send the full conversation history
    to the Foundry Agent and receive a reply.

    Workflow:
        1. If ``thread_id`` is None, create a new thread.
        2. Persist the user message.
        3. Retrieve the full message history.
        4. Send the history to the Foundry Agent via Responses API.
        5. Persist the agent reply.
        6. Return ``(reply, thread_id)``.

    Args:
        store: Initialised CosmosThreadStore instance.
        user_id: Owner's user identifier.
        user_message: Text of the user's message.
        thread_id: Existing thread ID to continue. Creates a new thread
            when ``None``.
        agent_name: Foundry Agent application name (e.g. ``"RAI-agent"``).
            Falls back to the ``FOUNDRY_AGENT_NAME`` environment variable.
            Used in the URL path.
        model_name: The agent's underlying model (e.g. ``"gpt-4.1-mini"``).
            Falls back to the ``FOUNDRY_MODEL_NAME`` environment variable.
            Must match the model configured in the Foundry agent.

    Returns:
        A ``(agent_reply, thread_id)`` tuple where ``agent_reply`` is the
        agent's text response and ``thread_id`` is the (possibly new) thread
        identifier.

    Raises:
        ThreadNotFoundError: The supplied ``thread_id`` does not exist or
            does not belong to ``user_id``.
        StorageConnectionError: Cosmos DB operation failed.
        ValueError: Required environment variables are not configured.
    """
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not project_endpoint:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT environment variable is required for "
            "agent integration. Set it in your .env file."
        )

    agent = agent_name or os.getenv("FOUNDRY_AGENT_NAME")
    if not agent:
        raise ValueError(
            "agent_name must be provided or FOUNDRY_AGENT_NAME environment "
            "variable must be set. This is the Foundry application name "
            "(e.g. 'RAI-agent')."
        )

    model = model_name or os.getenv("FOUNDRY_MODEL_NAME")
    if not model:
        raise ValueError(
            "model_name must be provided or FOUNDRY_MODEL_NAME environment "
            "variable must be set. Must match the agent's underlying model "
            "(e.g. 'gpt-4.1-mini')."
        )

    # Step 1: Ensure we have a thread
    if thread_id is None:
        thread = store.create_thread(user_id=user_id)
        thread_id = thread.id

    # Step 2: Persist user message
    store.append_message(thread_id, user_id, "user", user_message)

    # Step 3: Retrieve full conversation history
    messages = store.get_messages(thread_id, user_id)

    # Step 4: Build message payload and send via Responses API
    message_payload = [
        {"role": msg.role, "content": msg.content}
        for msg in messages
        if msg.role in ("user", "assistant")
    ]

    credential = DefaultAzureCredential()
    token = credential.get_token(_AZURE_ML_SCOPE).token

    base_url = (
        f"{project_endpoint.rstrip('/')}/applications/{agent}/protocols/openai"
    )

    openai_client = openai.OpenAI(
        base_url=base_url,
        api_key=token,
        default_query={"api-version": "2025-11-15-preview"},
    )
    response = openai_client.responses.create(
        model=model,
        input=message_payload,
    )
    reply = response.output_text

    # Step 5: Persist agent reply
    store.append_message(thread_id, user_id, "assistant", reply)

    return reply, thread_id

"""Foundry Agent integration for BYO Thread Storage (FR-006)."""

import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from src.thread_store import CosmosThreadStore


def run_agent_conversation(
    store: CosmosThreadStore,
    user_id: str,
    user_message: str,
    thread_id: str | None = None,
    agent_id: str | None = None,
) -> tuple[str, str]:
    """Run one turn of a Foundry Agent conversation with persistent history.

    Stores every message in Cosmos DB so the full conversation context is
    available for subsequent turns (FR-006, FR-007).

    Workflow:
        1. If ``thread_id`` is None, create a new thread.
        2. Persist the user message.
        3. Retrieve the full message history.
        4. Send the history to the Foundry Agent model.
        5. Persist the agent reply.
        6. Return ``(reply, thread_id)``.

    Args:
        store: Initialised CosmosThreadStore instance.
        user_id: Owner's user identifier.
        user_message: Text of the user's message.
        thread_id: Existing thread ID to continue. Creates a new thread
            when ``None``.
        agent_id: Foundry Agent ID. Uses the project's default agent when
            ``None``.

    Returns:
        A ``(agent_reply, thread_id)`` tuple where ``agent_reply`` is the
        agent's text response and ``thread_id`` is the (possibly new) thread
        identifier.

    Raises:
        ThreadNotFoundError: The supplied ``thread_id`` does not exist or
            does not belong to ``user_id``.
        StorageConnectionError: Cosmos DB operation failed.
        ValueError: ``AZURE_AI_PROJECT_ENDPOINT`` environment variable is
            not configured.
    """
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    if not project_endpoint:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT environment variable is required for "
            "agent integration. Set it in your .env file."
        )

    # Step 1: Ensure we have a thread
    if thread_id is None:
        thread = store.create_thread(user_id=user_id)
        thread_id = thread.id

    # Step 2: Persist user message
    store.append_message(thread_id, user_id, "user", user_message)

    # Step 3: Retrieve full conversation history
    messages = store.get_messages(thread_id, user_id)

    # Step 4: Build message payload and send to Foundry Agent
    message_payload = [
        {"role": msg.role, "content": msg.content} for msg in messages
    ]

    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=DefaultAzureCredential(),
    )

    with project_client:
        agents_client = project_client.agents
        if agent_id:
            agent = agents_client.get_agent(agent_id)
        else:
            # Use the first available agent in the project
            agents_list = list(agents_client.list_agents())
            if not agents_list:
                raise ValueError(
                    "No agents found in the Foundry project. "
                    "Deploy at least one agent model before using "
                    "run_agent_conversation()."
                )
            agent = agents_list[0]

        # Create a Foundry thread and inject the full conversation history
        # so the agent has complete context for this turn.
        foundry_thread = agents_client.create_thread()
        for hist_msg in message_payload:
            # Foundry Agents support "user" and "assistant" roles.
            # Skip "system" messages as they are set via the agent configuration.
            if hist_msg["role"] in ("user", "assistant"):
                agents_client.create_message(
                    thread_id=foundry_thread.id,
                    role=hist_msg["role"],
                    content=hist_msg["content"],
                )
        agents_client.create_and_process_run(
            thread_id=foundry_thread.id,
            agent_id=agent.id,
        )
        response_messages = agents_client.list_messages(
            thread_id=foundry_thread.id
        )
        reply = ""
        for resp_msg in response_messages.data:
            if resp_msg.role == "assistant":
                for part in resp_msg.content:
                    if hasattr(part, "text"):
                        reply = part.text.value
                        break
                if reply:
                    break

    # Step 5: Persist agent reply
    store.append_message(thread_id, user_id, "assistant", reply)

    return reply, thread_id

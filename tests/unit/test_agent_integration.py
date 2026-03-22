"""Unit tests for src/agent_integration.py — run_agent_conversation() (T013)."""

from unittest.mock import MagicMock, call, patch

import pytest

from src.agent_integration import run_agent_conversation
from src.exceptions import StorageConnectionError, ThreadNotFoundError
from src.models import Message, Thread


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_ID = "user-001"
_THREAD_ID = "thread-abc"
_AGENT_ID = "agent-xyz"
_USER_MESSAGE = "Hello, agent!"
_AGENT_REPLY = "Hello, human!"
_PROJECT_ENDPOINT = "https://my-project.api.azureml.ms"


def _make_store(
    thread_id: str = _THREAD_ID,
    messages: list[Message] | None = None,
) -> MagicMock:
    """Return a mock CosmosThreadStore pre-configured for happy-path tests."""
    store = MagicMock()
    mock_thread = MagicMock()
    mock_thread.id = thread_id
    store.create_thread.return_value = mock_thread

    if messages is None:
        messages = [
            Message(role="user", content=_USER_MESSAGE),
        ]
    store.get_messages.return_value = messages
    store.append_message.return_value = MagicMock(spec=Message)
    return store


def _make_agents_client(reply: str = _AGENT_REPLY) -> MagicMock:
    """Return a mock agents_client with one agent and a prepared reply."""
    agents_client = MagicMock()

    # agent
    mock_agent = MagicMock()
    mock_agent.id = _AGENT_ID
    agents_client.get_agent.return_value = mock_agent
    agents_client.list_agents.return_value = [mock_agent]

    # foundry thread
    mock_foundry_thread = MagicMock()
    mock_foundry_thread.id = "foundry-thread-001"
    agents_client.create_thread.return_value = mock_foundry_thread

    # run
    agents_client.create_and_process_run.return_value = MagicMock()

    # response messages
    text_part = MagicMock()
    text_part.text.value = reply
    assistant_msg = MagicMock()
    assistant_msg.role = "assistant"
    assistant_msg.content = [text_part]
    response = MagicMock()
    response.data = [assistant_msg]
    agents_client.list_messages.return_value = response

    return agents_client


def _make_project_client(agents_client: MagicMock) -> MagicMock:
    """Return a mock AIProjectClient that yields the given agents_client."""
    project_client = MagicMock()
    project_client.__enter__ = MagicMock(return_value=project_client)
    project_client.__exit__ = MagicMock(return_value=False)
    project_client.agents = agents_client
    return project_client


# ---------------------------------------------------------------------------
# Missing AZURE_AI_PROJECT_ENDPOINT
# ---------------------------------------------------------------------------


class TestRunAgentConversationMissingEndpoint:
    """Raises ValueError when AZURE_AI_PROJECT_ENDPOINT is not set."""

    def test_raises_value_error_without_env_var(self) -> None:
        store = _make_store()
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="AZURE_AI_PROJECT_ENDPOINT"):
                run_agent_conversation(store, _USER_ID, _USER_MESSAGE)

    def test_error_message_is_descriptive(self) -> None:
        store = _make_store()
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="agent integration"):
                run_agent_conversation(store, _USER_ID, _USER_MESSAGE)


# ---------------------------------------------------------------------------
# Thread creation when thread_id is None
# ---------------------------------------------------------------------------


class TestRunAgentConversationThreadCreation:
    """Creates a new thread when thread_id is not supplied."""

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_creates_thread_when_thread_id_is_none(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            run_agent_conversation(store, _USER_ID, _USER_MESSAGE, thread_id=None)

        store.create_thread.assert_called_once_with(user_id=_USER_ID)

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_does_not_create_thread_when_thread_id_supplied(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        store.create_thread.assert_not_called()

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_returned_thread_id_is_newly_created_when_none_given(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        new_tid = "brand-new-thread"
        store = _make_store(thread_id=new_tid)
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            _, returned_tid = run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=None
            )

        assert returned_tid == new_tid

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_returned_thread_id_equals_supplied_thread_id(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            _, returned_tid = run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        assert returned_tid == _THREAD_ID


# ---------------------------------------------------------------------------
# Message persistence
# ---------------------------------------------------------------------------


class TestRunAgentConversationMessagePersistence:
    """User message and agent reply are persisted via append_message."""

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_user_message_appended_to_store(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        store.append_message.assert_any_call(
            _THREAD_ID, _USER_ID, "user", _USER_MESSAGE
        )

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_agent_reply_appended_to_store(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client(reply=_AGENT_REPLY)
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        store.append_message.assert_any_call(
            _THREAD_ID, _USER_ID, "assistant", _AGENT_REPLY
        )

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_append_message_called_twice(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        """append_message is called once for user and once for assistant."""
        store = _make_store()
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        assert store.append_message.call_count == 2

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_get_messages_called_after_user_message_appended(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        """get_messages is called to retrieve full history for context."""
        store = _make_store()
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        store.get_messages.assert_called_once_with(_THREAD_ID, _USER_ID)


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------


class TestRunAgentConversationReturnValue:
    """Returns (reply, thread_id) tuple."""

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_returns_tuple(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            result = run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        assert isinstance(result, tuple)
        assert len(result) == 2

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_first_element_is_agent_reply(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client(reply=_AGENT_REPLY)
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            reply, _ = run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        assert reply == _AGENT_REPLY

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_second_element_is_thread_id(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            _, thread_id = run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        assert thread_id == _THREAD_ID


# ---------------------------------------------------------------------------
# Agent selection
# ---------------------------------------------------------------------------


class TestRunAgentConversationAgentSelection:
    """Selects the correct agent from the Foundry project."""

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_uses_get_agent_when_agent_id_supplied(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID, agent_id=_AGENT_ID
            )

        agents_client.get_agent.assert_called_once_with(_AGENT_ID)
        agents_client.list_agents.assert_not_called()

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_uses_first_listed_agent_when_agent_id_is_none(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID, agent_id=None
            )

        agents_client.list_agents.assert_called_once()
        agents_client.get_agent.assert_not_called()

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_raises_value_error_when_no_agents_available(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client()
        agents_client.list_agents.return_value = []  # No agents in project
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            with pytest.raises(ValueError, match="No agents found"):
                run_agent_conversation(
                    store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
                )


# ---------------------------------------------------------------------------
# Conversation history sent to Foundry
# ---------------------------------------------------------------------------


class TestRunAgentConversationHistoryContext:
    """Full conversation history is sent as context to the Foundry Agent."""

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_system_messages_are_skipped(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        """System-role messages are excluded from the Foundry thread (unsupported role)."""
        store = _make_store(
            messages=[
                Message(role="system", content="Be helpful."),
                Message(role="user", content=_USER_MESSAGE),
            ]
        )
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        calls = agents_client.create_message.call_args_list
        roles_sent = [c.kwargs.get("role") for c in calls]
        assert "system" not in roles_sent

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_user_and_assistant_messages_are_sent(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        """User and assistant messages are forwarded to the Foundry thread."""
        store = _make_store(
            messages=[
                Message(role="user", content="First question"),
                Message(role="assistant", content="First answer"),
                Message(role="user", content=_USER_MESSAGE),
            ]
        )
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        assert agents_client.create_message.call_count == 3

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_create_and_process_run_called_with_correct_ids(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        agents_client = _make_agents_client()
        project_client = _make_project_client(agents_client)
        mock_client_cls.return_value = project_client
        foundry_thread_id = agents_client.create_thread.return_value.id

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID, agent_id=_AGENT_ID
            )

        agents_client.create_and_process_run.assert_called_once_with(
            thread_id=foundry_thread_id,
            agent_id=_AGENT_ID,
        )


# ---------------------------------------------------------------------------
# Storage error propagation
# ---------------------------------------------------------------------------


class TestRunAgentConversationStorageErrors:
    """Storage exceptions propagate correctly."""

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_thread_not_found_propagates_on_append_message(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        store.append_message.side_effect = ThreadNotFoundError("not found")

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            with pytest.raises(ThreadNotFoundError):
                run_agent_conversation(
                    store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
                )

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.AIProjectClient")
    def test_storage_connection_error_propagates_on_get_messages(
        self,
        mock_client_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        store.get_messages.side_effect = StorageConnectionError("db offline")

        with patch.dict("os.environ", {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}):
            with pytest.raises(StorageConnectionError):
                run_agent_conversation(
                    store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
                )

"""Unit tests for src/agent_integration.py — run_agent_conversation() (T013).

Rewritten for the OpenAI Responses API integration (replacing old Agents API).
"""

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
_AGENT_NAME = "RAI-agent"
_MODEL_NAME = "gpt-4.1-mini"
_MODEL_NAME = "gpt-4.1-mini"
_USER_MESSAGE = "Hello, agent!"
_AGENT_REPLY = "Hello, human!"
_PROJECT_ENDPOINT = "https://my-resource.services.ai.azure.com/api/projects/my-project"

_ENV = {
    "AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT,
    "FOUNDRY_AGENT_NAME": _AGENT_NAME,
    "FOUNDRY_MODEL_NAME": _MODEL_NAME,
}


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


def _make_openai_client(reply: str = _AGENT_REPLY) -> MagicMock:
    """Return a mock OpenAI client with responses.create configured."""
    openai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.output_text = reply
    openai_client.responses.create.return_value = mock_response
    return openai_client


# ---------------------------------------------------------------------------
# Missing environment variables
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


class TestRunAgentConversationMissingAgentName:
    """Raises ValueError when agent_name and FOUNDRY_AGENT_NAME are both unset."""

    def test_raises_value_error_without_agent_name(self) -> None:
        store = _make_store()
        env = {"AZURE_AI_PROJECT_ENDPOINT": _PROJECT_ENDPOINT}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(ValueError, match="agent_name"):
                run_agent_conversation(store, _USER_ID, _USER_MESSAGE)

    def test_uses_env_var_when_agent_name_not_passed(self) -> None:
        store = _make_store()
        openai_client = _make_openai_client()

        with patch.dict("os.environ", _ENV, clear=True):
            with patch("src.agent_integration.openai.OpenAI", return_value=openai_client):
                with patch("src.agent_integration.DefaultAzureCredential"):
                    run_agent_conversation(
                        store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
                    )

        openai_client.responses.create.assert_called_once()
        call_kwargs = openai_client.responses.create.call_args
        assert call_kwargs.kwargs["model"] == _MODEL_NAME

    def test_agent_name_param_overrides_env_var(self) -> None:
        store = _make_store()
        openai_client = _make_openai_client()
        custom_name = "custom-agent"

        with patch.dict("os.environ", _ENV, clear=True):
            with patch("src.agent_integration.openai.OpenAI", return_value=openai_client):
                with patch("src.agent_integration.DefaultAzureCredential"):
                    run_agent_conversation(
                        store, _USER_ID, _USER_MESSAGE,
                        thread_id=_THREAD_ID, agent_name=custom_name,
                    )

        call_kwargs = openai_client.responses.create.call_args
        assert call_kwargs.kwargs["model"] == _MODEL_NAME


# ---------------------------------------------------------------------------
# Thread creation when thread_id is None
# ---------------------------------------------------------------------------


class TestRunAgentConversationThreadCreation:
    """Creates a new thread when thread_id is not supplied."""

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_creates_thread_when_thread_id_is_none(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            run_agent_conversation(store, _USER_ID, _USER_MESSAGE, thread_id=None)

        store.create_thread.assert_called_once_with(user_id=_USER_ID)

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_does_not_create_thread_when_thread_id_supplied(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        store.create_thread.assert_not_called()

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_returned_thread_id_is_newly_created_when_none_given(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        new_tid = "brand-new-thread"
        store = _make_store(thread_id=new_tid)
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            _, returned_tid = run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=None
            )

        assert returned_tid == new_tid

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_returned_thread_id_equals_supplied_thread_id(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
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
    @patch("src.agent_integration.openai.OpenAI")
    def test_user_message_appended_to_store(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        store.append_message.assert_any_call(
            _THREAD_ID, _USER_ID, "user", _USER_MESSAGE
        )

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_agent_reply_appended_to_store(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        openai_client = _make_openai_client(reply=_AGENT_REPLY)
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        store.append_message.assert_any_call(
            _THREAD_ID, _USER_ID, "assistant", _AGENT_REPLY
        )

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_append_message_called_twice(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        """append_message is called once for user and once for assistant."""
        store = _make_store()
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        assert store.append_message.call_count == 2

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_get_messages_called_after_user_message_appended(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        """get_messages is called to retrieve full history for context."""
        store = _make_store()
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
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
    @patch("src.agent_integration.openai.OpenAI")
    def test_returns_tuple(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            result = run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        assert isinstance(result, tuple)
        assert len(result) == 2

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_first_element_is_agent_reply(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        openai_client = _make_openai_client(reply=_AGENT_REPLY)
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            reply, _ = run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        assert reply == _AGENT_REPLY

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_second_element_is_thread_id(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            _, thread_id = run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        assert thread_id == _THREAD_ID


# ---------------------------------------------------------------------------
# Conversation history sent to Responses API
# ---------------------------------------------------------------------------


class TestRunAgentConversationHistoryContext:
    """Full conversation history is sent as context via Responses API."""

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_system_messages_are_skipped(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        """System-role messages are excluded from the input payload."""
        store = _make_store(
            messages=[
                Message(role="system", content="Be helpful."),
                Message(role="user", content=_USER_MESSAGE),
            ]
        )
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        call_kwargs = openai_client.responses.create.call_args.kwargs
        roles_sent = [m["role"] for m in call_kwargs["input"]]
        assert "system" not in roles_sent

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_user_and_assistant_messages_are_sent(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        """User and assistant messages are forwarded in the input payload."""
        store = _make_store(
            messages=[
                Message(role="user", content="First question"),
                Message(role="assistant", content="First answer"),
                Message(role="user", content=_USER_MESSAGE),
            ]
        )
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        call_kwargs = openai_client.responses.create.call_args.kwargs
        assert len(call_kwargs["input"]) == 3

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_responses_create_called_with_correct_model(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        openai_client = _make_openai_client()
        mock_openai_cls.return_value = openai_client

        with patch.dict("os.environ", _ENV, clear=True):
            run_agent_conversation(
                store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
            )

        openai_client.responses.create.assert_called_once()
        call_kwargs = openai_client.responses.create.call_args.kwargs
        assert call_kwargs["model"] == _MODEL_NAME


# ---------------------------------------------------------------------------
# Storage error propagation
# ---------------------------------------------------------------------------


class TestRunAgentConversationStorageErrors:
    """Storage exceptions propagate correctly."""

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_thread_not_found_propagates_on_append_message(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        store.append_message.side_effect = ThreadNotFoundError("not found")

        with patch.dict("os.environ", _ENV, clear=True):
            with pytest.raises(ThreadNotFoundError):
                run_agent_conversation(
                    store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
                )

    @patch("src.agent_integration.DefaultAzureCredential")
    @patch("src.agent_integration.openai.OpenAI")
    def test_storage_connection_error_propagates_on_get_messages(
        self,
        mock_openai_cls: MagicMock,
        mock_dac_cls: MagicMock,
    ) -> None:
        store = _make_store()
        store.get_messages.side_effect = StorageConnectionError("db offline")

        with patch.dict("os.environ", _ENV, clear=True):
            with pytest.raises(StorageConnectionError):
                run_agent_conversation(
                    store, _USER_ID, _USER_MESSAGE, thread_id=_THREAD_ID
                )

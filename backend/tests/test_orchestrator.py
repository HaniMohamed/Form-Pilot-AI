"""
Unit tests for the markdown-driven FormOrchestrator.

Uses a mock LLM to test deterministically without API calls.

Tests cover:
- Initial action (greeting MESSAGE)
- Extraction phase: multi_answer parsing and answer storage
- Conversation phase: LLM returns ASK_*, TOOL_CALL, FORM_COMPLETE
- Tool call round-trip: AI requests tool → results sent back → AI continues
- LLM JSON parse failure triggers retry / fallback
- Conversation history is maintained
"""

import json
from unittest.mock import MagicMock

import pytest

from backend.agent.orchestrator import FormOrchestrator


# Minimal markdown form context for tests
SIMPLE_FORM_MD = """
# Simple Test Form

## Fields
- **name** (text, required): What is your name?
- **color** (dropdown, required): What is your favorite color?
  Options: Red, Blue, Green
"""

TOOL_FORM_MD = """
# Tool Test Form

## Tools
- `get_options`: Returns available options for a field
- `set_field_value(fieldId, value)`: Sets a field value

## Fields
- **establishment** (dropdown, required): Select your establishment
  Data source: call `get_options` to get the list
- **name** (text, required): Your name?
"""


# --- Mock LLM ---


class MockLLM:
    """A mock LLM that returns pre-configured responses.

    Set `responses` to a list of dicts (the JSON the LLM would return).
    Each call to ainvoke pops the next response.
    """

    def __init__(self, responses: list[dict] | None = None):
        self.responses = list(responses or [])
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        if not self.responses:
            raise RuntimeError("MockLLM has no more responses")
        response_dict = self.responses.pop(0)
        result = MagicMock()
        result.content = json.dumps(response_dict)
        return result


class MockLLMRawText:
    """A mock LLM that returns raw text strings (not necessarily JSON)."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        if not self.responses:
            raise RuntimeError("MockLLMRawText has no more responses")
        result = MagicMock()
        result.content = self.responses.pop(0)
        return result


class MockLLMError:
    """A mock LLM that always raises an exception."""

    def __init__(self):
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        raise Exception("LLM connection failed")


# =============================================================
# Test: Initial action (greeting MESSAGE)
# =============================================================


class TestInitialAction:
    """Tests for get_initial_action."""

    def test_returns_greeting_message(self):
        """Initial action is a MESSAGE asking user to describe all data."""
        llm = MockLLM()
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        action = orch.get_initial_action()
        assert action["action"] == "MESSAGE"
        assert "text" in action
        assert "FormPilot AI" in action["text"]

    def test_records_in_conversation_history(self):
        llm = MockLLM()
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        orch.get_initial_action()
        assert len(orch.conversation_history) == 1
        assert orch.conversation_history[0]["role"] == "assistant"


# =============================================================
# Test: Extraction phase (multi_answer)
# =============================================================


class TestExtractionPhase:
    """Tests for the bulk extraction phase."""

    @pytest.mark.asyncio
    async def test_extracts_answers_from_multi_answer(self):
        """Extraction captures answers and stores them."""
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {"name": "Alice", "color": "Blue"},
             "message": "Captured both fields."},
            # After extraction, conversation phase should return FORM_COMPLETE
            {"action": "FORM_COMPLETE", "data": {"name": "Alice", "color": "Blue"},
             "message": "All done!"},
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        result = await orch.process_user_message("My name is Alice and I like Blue")
        assert orch.answers["name"] == "Alice"
        assert orch.answers["color"] == "Blue"

    @pytest.mark.asyncio
    async def test_empty_extraction_falls_through(self):
        """Empty extraction results → falls through to conversation phase."""
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {},
             "message": "Couldn't extract anything."},
            # Conversation phase should ask for the first field
            {"action": "ASK_TEXT", "field_id": "name", "label": "What is your name?",
             "message": "Let's start with your name."},
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        result = await orch.process_user_message("hello")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"

    @pytest.mark.asyncio
    async def test_extraction_marks_done(self):
        """After extraction, subsequent messages go to conversation phase."""
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {"name": "Alice"},
             "message": "Got name."},
            # Conversation phase
            {"action": "ASK_DROPDOWN", "field_id": "color",
             "label": "Favorite color?", "options": ["Red", "Blue", "Green"],
             "message": "Now, what's your favorite color?"},
            # Answer color
            {"action": "FORM_COMPLETE", "data": {"name": "Alice", "color": "Blue"},
             "message": "All done!"},
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        assert orch._initial_extraction_done is False

        await orch.process_user_message("My name is Alice")
        assert orch._initial_extraction_done is True

        # Second message should go to conversation phase
        result = await orch.process_user_message("Blue")
        assert result["action"] == "FORM_COMPLETE"


# =============================================================
# Test: Conversation phase (LLM returns actions directly)
# =============================================================


class TestConversationPhase:
    """Tests for the LLM-driven conversation phase."""

    @pytest.mark.asyncio
    async def test_ask_text_action(self):
        """LLM returns ASK_TEXT action after extraction."""
        llm = MockLLM([
            # Extraction: nothing found
            {"intent": "multi_answer", "answers": {},
             "message": "Nothing extracted."},
            # Conversation phase (called right after extraction falls through)
            {"action": "ASK_TEXT", "field_id": "name",
             "label": "What is your name?",
             "message": "Please tell me your name."},
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        # First message triggers extraction + conversation
        result = await orch.process_user_message("hi")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"

    @pytest.mark.asyncio
    async def test_ask_dropdown_with_options(self):
        """LLM returns ASK_DROPDOWN with options."""
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {"name": "Alice"},
             "message": "Got name."},
            {"action": "ASK_DROPDOWN", "field_id": "color",
             "label": "Favorite color?", "options": ["Red", "Blue", "Green"],
             "message": "Choose a color."},
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        result = await orch.process_user_message("My name is Alice")
        assert result["action"] == "ASK_DROPDOWN"
        assert result["options"] == ["Red", "Blue", "Green"]

    @pytest.mark.asyncio
    async def test_form_complete(self):
        """LLM returns FORM_COMPLETE."""
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {"name": "Alice", "color": "Red"},
             "message": "All captured."},
            {"action": "FORM_COMPLETE",
             "data": {"name": "Alice", "color": "Red"},
             "message": "Form complete!"},
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        result = await orch.process_user_message("Alice, Red")
        assert result["action"] == "FORM_COMPLETE"
        assert result["data"]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_form_complete_populates_data_from_answers(self):
        """If LLM returns FORM_COMPLETE without data, answers are used."""
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {"name": "Bob", "color": "Green"},
             "message": "Got everything."},
            {"action": "FORM_COMPLETE", "message": "All done!"},
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        result = await orch.process_user_message("Bob, Green")
        assert result["action"] == "FORM_COMPLETE"
        assert result["data"]["name"] == "Bob"
        assert result["data"]["color"] == "Green"


# =============================================================
# Test: Tool call round-trip
# =============================================================


class TestToolCallRoundTrip:
    """Test TOOL_CALL action and tool result handling."""

    @pytest.mark.asyncio
    async def test_tool_call_returned_to_frontend(self):
        """LLM can request a TOOL_CALL action."""
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {},
             "message": "Let me get your data."},
            {"action": "TOOL_CALL", "tool_name": "get_options",
             "tool_args": {}, "message": "Fetching options..."},
        ])
        orch = FormOrchestrator(TOOL_FORM_MD, llm)

        result = await orch.process_user_message("Start")
        assert result["action"] == "TOOL_CALL"
        assert result["tool_name"] == "get_options"

    @pytest.mark.asyncio
    async def test_tool_results_sent_back_to_llm(self):
        """Tool results are sent back and LLM continues the conversation."""
        llm = MockLLM([
            # Extraction
            {"intent": "multi_answer", "answers": {},
             "message": "I need to get your data."},
            # Conversation: request tool call
            {"action": "TOOL_CALL", "tool_name": "get_options",
             "tool_args": {}, "message": "Fetching options..."},
            # After tool results: present options
            {"action": "ASK_DROPDOWN", "field_id": "establishment",
             "label": "Select establishment",
             "options": ["Company A", "Company B"],
             "message": "Please select your establishment."},
        ])
        orch = FormOrchestrator(TOOL_FORM_MD, llm)

        # Initial message triggers extraction + conversation → TOOL_CALL
        r1 = await orch.process_user_message("Start")
        assert r1["action"] == "TOOL_CALL"

        # Send tool results back
        tool_results = [{
            "tool_name": "get_options",
            "result": {"options": ["Company A", "Company B"]},
        }]
        r2 = await orch.process_user_message("", tool_results=tool_results)
        assert r2["action"] == "ASK_DROPDOWN"
        assert "Company A" in r2["options"]

    @pytest.mark.asyncio
    async def test_tool_results_added_to_history(self):
        """Tool results should appear in conversation history."""
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {},
             "message": "Need data."},
            {"action": "TOOL_CALL", "tool_name": "get_options",
             "tool_args": {}, "message": "Fetching..."},
            {"action": "ASK_TEXT", "field_id": "name",
             "label": "Name?", "message": "What's your name?"},
        ])
        orch = FormOrchestrator(TOOL_FORM_MD, llm)

        await orch.process_user_message("Start")

        tool_results = [{
            "tool_name": "get_options",
            "result": {"options": ["A", "B"]},
        }]
        await orch.process_user_message("", tool_results=tool_results)

        # Check that tool result is in history
        history_contents = [msg["content"] for msg in orch.conversation_history]
        tool_history = [c for c in history_contents if "Tool result" in c]
        assert len(tool_history) >= 1


# =============================================================
# Test: LLM JSON failure and retry
# =============================================================


class TestLLMJsonFailure:
    """Test behavior when LLM returns invalid JSON or fails entirely."""

    @pytest.mark.asyncio
    async def test_invalid_json_then_valid_retry(self):
        llm = MockLLMRawText([
            # Extraction phase — invalid JSON then valid retry
            "I'm not sure what you mean",
            '{"intent": "multi_answer", "answers": {}, "message": "Nothing extracted."}',
            # Conversation phase
            '{"action": "ASK_TEXT", "field_id": "name", "label": "Name?", "message": "Your name?"}',
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        result = await orch.process_user_message("hello")
        assert result["action"] == "ASK_TEXT"
        assert llm.call_count >= 2  # At least extraction retry + conversation

    @pytest.mark.asyncio
    async def test_all_retries_fail_returns_message(self):
        llm = MockLLMRawText([
            "not json 1",
            "not json 2",
            "not json 3",
            # Conversation phase also fails
            "still not json",
            "also not json",
            "nope",
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        result = await orch.process_user_message("hello")
        assert result["action"] == "MESSAGE"
        assert "trouble" in result["text"]

    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(self):
        llm = MockLLMError()
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        result = await orch.process_user_message("hello")
        assert result["action"] == "MESSAGE"
        assert "trouble" in result["text"]

    @pytest.mark.asyncio
    async def test_json_in_markdown_fence_extracted(self):
        llm = MockLLMRawText([
            '```json\n{"intent": "multi_answer", "answers": {"name": "Alice"}, "message": "Got it!"}\n```',
            '{"action": "ASK_DROPDOWN", "field_id": "color", "label": "Color?", "options": ["Red", "Blue", "Green"], "message": "Color?"}',
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        await orch.process_user_message("Alice")
        assert orch.answers.get("name") == "Alice"


# =============================================================
# Test: Conversation history
# =============================================================


class TestConversationHistory:
    """Test that conversation history is maintained."""

    @pytest.mark.asyncio
    async def test_messages_recorded(self):
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {"name": "Alice"},
             "message": "Got name."},
            {"action": "ASK_DROPDOWN", "field_id": "color", "label": "Color?",
             "options": ["Red", "Blue", "Green"],
             "message": "What color?"},
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        await orch.process_user_message("Alice")

        roles = [m["role"] for m in orch.conversation_history]
        assert "user" in roles
        assert "assistant" in roles

    @pytest.mark.asyncio
    async def test_initial_action_recorded(self):
        llm = MockLLM()
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        orch.get_initial_action()
        assert len(orch.conversation_history) == 1
        assert orch.conversation_history[0]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_history_grows_with_turns(self):
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {},
             "message": "Nothing found."},
            {"action": "ASK_TEXT", "field_id": "name",
             "label": "Name?", "message": "Your name?"},
            {"action": "ASK_DROPDOWN", "field_id": "color",
             "label": "Color?", "options": ["Red", "Blue", "Green"],
             "message": "What color?"},
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)
        orch.get_initial_action()

        # After initial: 1 entry
        assert len(orch.conversation_history) == 1

        await orch.process_user_message("hello")
        # user + extraction msg + conversation msg
        assert len(orch.conversation_history) >= 3

        await orch.process_user_message("Alice")
        assert len(orch.conversation_history) >= 5


# =============================================================
# Test: Answer tracking
# =============================================================


class TestAnswerTracking:
    """Test that answers are tracked by the orchestrator."""

    @pytest.mark.asyncio
    async def test_answers_from_extraction(self):
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {"name": "Bob", "color": "Red"},
             "message": "All captured."},
            {"action": "FORM_COMPLETE", "data": {"name": "Bob", "color": "Red"},
             "message": "Done!"},
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        await orch.process_user_message("Bob, Red")
        assert orch.get_answers() == {"name": "Bob", "color": "Red"}

    @pytest.mark.asyncio
    async def test_answers_accumulate_across_turns(self):
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {"name": "Alice"},
             "message": "Got name."},
            {"action": "ASK_DROPDOWN", "field_id": "color",
             "label": "Color?", "options": ["Red", "Blue", "Green"],
             "message": "Color?"},
        ])
        orch = FormOrchestrator(SIMPLE_FORM_MD, llm)

        await orch.process_user_message("Alice")
        assert "name" in orch.get_answers()
        assert orch.get_answers()["name"] == "Alice"

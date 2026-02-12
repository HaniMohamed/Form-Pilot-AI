"""
Unit tests for the FormOrchestrator.

Uses a mock LLM to test deterministically without API calls.

Tests cover:
- Initial action (greeting + first question)
- Happy path: sequential field answers until FORM_COMPLETE
- Correction flow: change a previously answered field
- Visibility cascade: answering a field reveals a new conditional field
- Invalid dropdown value handling
- LLM JSON parse failure triggers retry / fallback
- Conversation history is maintained
- Clarification / unknown intent handling
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agent.orchestrator import FormOrchestrator
from backend.core.form_state import FormStateManager
from backend.core.schema import FormSchema

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


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


# --- Fixtures ---


@pytest.fixture
def incident_schema() -> FormSchema:
    with open(SCHEMAS_DIR / "incident_report.json") as f:
        return FormSchema(**json.load(f))


@pytest.fixture
def leave_schema() -> FormSchema:
    with open(SCHEMAS_DIR / "leave_request.json") as f:
        return FormSchema(**json.load(f))


@pytest.fixture
def simple_schema() -> FormSchema:
    return FormSchema(
        form_id="simple",
        fields=[
            {"id": "name", "type": "text", "required": True, "prompt": "What is your name?"},
            {"id": "color", "type": "dropdown", "required": True, "prompt": "Favorite color?", "options": ["Red", "Blue", "Green"]},
        ],
    )


# =============================================================
# Test: Initial action
# =============================================================


class TestInitialAction:
    """Tests for get_initial_action."""

    def test_returns_first_field_action(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLM()
        orch = FormOrchestrator(mgr, llm)

        action = orch.get_initial_action()
        assert action["action"] == "ASK_TEXT"
        assert action["field_id"] == "name"
        assert "message" in action

    def test_returns_dropdown_for_incident(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        llm = MockLLM()
        orch = FormOrchestrator(mgr, llm)

        action = orch.get_initial_action()
        assert action["action"] == "ASK_DROPDOWN"
        assert action["field_id"] == "incident_type"
        assert action["options"] == ["Fire", "Accident", "Injury"]

    def test_records_in_conversation_history(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLM()
        orch = FormOrchestrator(mgr, llm)

        orch.get_initial_action()
        history = mgr.get_conversation_history()
        assert len(history) == 1
        assert history[0]["role"] == "assistant"


# =============================================================
# Test: Happy path — sequential answers
# =============================================================


class TestHappyPath:
    """Test answering fields sequentially until form complete."""

    @pytest.mark.asyncio
    async def test_simple_form_completion(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            {"intent": "answer", "field_id": "name", "value": "Alice", "message": "Got it!"},
            {"intent": "answer", "field_id": "color", "value": "Blue", "message": "Great choice!"},
        ])
        orch = FormOrchestrator(mgr, llm)

        # Answer name
        result1 = await orch.process_user_message("My name is Alice")
        assert result1["action"] == "ASK_DROPDOWN"
        assert result1["field_id"] == "color"
        assert mgr.get_answer("name") == "Alice"

        # Answer color
        result2 = await orch.process_user_message("Blue")
        assert result2["action"] == "FORM_COMPLETE"
        assert result2["data"]["name"] == "Alice"
        assert result2["data"]["color"] == "Blue"

    @pytest.mark.asyncio
    async def test_incident_report_full_flow(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        llm = MockLLM([
            {"intent": "answer", "field_id": "incident_type", "value": "Accident", "message": "Noted."},
            {"intent": "answer", "field_id": "start_date", "value": "2026-02-11", "message": "OK."},
            {"intent": "answer", "field_id": "end_date", "value": "2026-02-15", "message": "Got it."},
            {"intent": "answer", "field_id": "followup_reason", "value": "Extended duration", "message": "Thanks."},
            {"intent": "answer", "field_id": "location", "value": {"lat": 24.7, "lng": 46.6}, "message": "Done."},
        ])
        orch = FormOrchestrator(mgr, llm)

        r1 = await orch.process_user_message("Accident")
        assert r1["field_id"] == "start_date"

        r2 = await orch.process_user_message("Feb 11, 2026")
        assert r2["field_id"] == "end_date"

        r3 = await orch.process_user_message("Feb 15, 2026")
        # followup_reason should appear since end > start
        assert r3["field_id"] == "followup_reason"

        r4 = await orch.process_user_message("Extended duration")
        assert r4["field_id"] == "location"

        r5 = await orch.process_user_message("Riyadh office")
        assert r5["action"] == "FORM_COMPLETE"
        assert len(r5["data"]) == 5


# =============================================================
# Test: Correction flow
# =============================================================


class TestCorrectionFlow:
    """Test that users can correct previously answered fields."""

    @pytest.mark.asyncio
    async def test_correction_clears_and_re_asks(self, simple_schema):
        mgr = FormStateManager(simple_schema)

        # Pre-fill name
        mgr.set_answer("name", "Alice")

        llm = MockLLM([
            {"intent": "correction", "field_id": "name", "message": "Sure, let's change your name."},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("I want to change my name")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"
        assert mgr.get_answer("name") is None

    @pytest.mark.asyncio
    async def test_correction_then_new_answer(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.set_answer("name", "Alice")

        llm = MockLLM([
            {"intent": "correction", "field_id": "name", "message": "Sure."},
            {"intent": "answer", "field_id": "name", "value": "Bob", "message": "Updated!"},
        ])
        orch = FormOrchestrator(mgr, llm)

        # Correction
        r1 = await orch.process_user_message("Change my name")
        assert r1["field_id"] == "name"

        # New answer
        r2 = await orch.process_user_message("Bob")
        assert mgr.get_answer("name") == "Bob"


# =============================================================
# Test: Visibility cascade
# =============================================================


class TestVisibilityCascade:
    """Test that answering a field can reveal conditional fields."""

    @pytest.mark.asyncio
    async def test_end_date_reveals_followup_reason(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")

        llm = MockLLM([
            {"intent": "answer", "field_id": "end_date", "value": "2026-02-15", "message": "OK."},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("Feb 15")
        # followup_reason should now be the next field
        assert result["field_id"] == "followup_reason"

    @pytest.mark.asyncio
    async def test_same_date_skips_followup(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")

        llm = MockLLM([
            {"intent": "answer", "field_id": "end_date", "value": "2026-02-10", "message": "OK."},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("Feb 10")
        # followup_reason hidden — should go to location
        assert result["field_id"] == "location"


# =============================================================
# Test: Invalid answer handling
# =============================================================


class TestInvalidAnswer:
    """Test that invalid answers are rejected gracefully."""

    @pytest.mark.asyncio
    async def test_invalid_dropdown_re_asks(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.set_answer("name", "Alice")

        llm = MockLLM([
            {"intent": "answer", "field_id": "color", "value": "Purple", "message": "Purple it is!"},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("Purple")
        # Should re-ask color since Purple is not a valid option
        assert result["action"] == "ASK_DROPDOWN"
        assert result["field_id"] == "color"
        assert "doesn't look right" in result["message"]

    @pytest.mark.asyncio
    async def test_answer_without_value_re_asks(self, simple_schema):
        mgr = FormStateManager(simple_schema)

        llm = MockLLM([
            {"intent": "answer", "field_id": "name", "value": None, "message": "Hmm"},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("hello")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"


# =============================================================
# Test: LLM JSON failure and retry
# =============================================================


class TestLLMJsonFailure:
    """Test behavior when LLM returns invalid JSON or fails entirely."""

    @pytest.mark.asyncio
    async def test_invalid_json_then_valid_retry(self, simple_schema):
        mgr = FormStateManager(simple_schema)

        llm = MockLLMRawText([
            "I'm not sure what you mean",  # Invalid JSON
            '{"intent": "ask", "message": "What is your name?"}',  # Valid retry
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("hello")
        assert result["action"] == "ASK_TEXT"
        assert llm.call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_fail_returns_fallback(self, simple_schema):
        mgr = FormStateManager(simple_schema)

        llm = MockLLMRawText([
            "not json 1",
            "not json 2",
            "not json 3",
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("hello")
        assert result["action"] == "MESSAGE"
        assert "trouble understanding" in result["text"]

    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLMError()
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("hello")
        assert result["action"] == "MESSAGE"
        assert "trouble understanding" in result["text"]

    @pytest.mark.asyncio
    async def test_json_in_markdown_fence_extracted(self, simple_schema):
        mgr = FormStateManager(simple_schema)

        llm = MockLLMRawText([
            '```json\n{"intent": "answer", "field_id": "name", "value": "Alice", "message": "Got it!"}\n```',
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("Alice")
        assert mgr.get_answer("name") == "Alice"


# =============================================================
# Test: Conversation history
# =============================================================


class TestConversationHistory:
    """Test that conversation history is maintained."""

    @pytest.mark.asyncio
    async def test_messages_recorded(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            {"intent": "answer", "field_id": "name", "value": "Alice", "message": "Got it!"},
        ])
        orch = FormOrchestrator(mgr, llm)

        await orch.process_user_message("Alice")
        history = mgr.get_conversation_history()

        # Should have: user message + assistant response
        roles = [m["role"] for m in history]
        assert "user" in roles
        assert "assistant" in roles

    @pytest.mark.asyncio
    async def test_initial_action_recorded(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLM()
        orch = FormOrchestrator(mgr, llm)

        orch.get_initial_action()
        history = mgr.get_conversation_history()
        assert len(history) == 1
        assert history[0]["role"] == "assistant"


# =============================================================
# Test: Clarify intent
# =============================================================


class TestClarifyIntent:
    """Test handling of clarification and unknown intents."""

    @pytest.mark.asyncio
    async def test_clarify_re_presents_field(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            {"intent": "clarify", "message": "Could you please provide your name?"},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("what?")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"

    @pytest.mark.asyncio
    async def test_unknown_intent_treated_as_clarify(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            {"intent": "unknown_thing", "message": "I'm not sure."},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("blah")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"


# =============================================================
# Test: Form already complete
# =============================================================


class TestFormAlreadyComplete:
    """Test processing messages when the form is already complete."""

    @pytest.mark.asyncio
    async def test_returns_complete_when_already_done(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.set_answer("name", "Alice")
        mgr.set_answer("color", "Red")

        llm = MockLLM()  # Should not be called
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("anything")
        assert result["action"] == "FORM_COMPLETE"
        assert llm.call_count == 0

"""
Unit tests for the FormOrchestrator.

Uses a mock LLM to test deterministically without API calls.

Tests cover:
- Initial action (greeting MESSAGE)
- Happy path: extraction then sequential field answers until FORM_COMPLETE
- Correction flow: change a previously answered field
- Visibility cascade: answering a field reveals a new conditional field
- Invalid dropdown value handling
- LLM JSON parse failure triggers retry / fallback
- Conversation history is maintained
- Clarification / unknown intent handling
- Multi-answer (bulk extraction) handling
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
# Test: Initial action (now returns MESSAGE greeting)
# =============================================================


class TestInitialAction:
    """Tests for get_initial_action."""

    def test_returns_greeting_message(self, simple_schema):
        """Initial action is now a MESSAGE asking user to describe all data."""
        mgr = FormStateManager(simple_schema)
        llm = MockLLM()
        orch = FormOrchestrator(mgr, llm)

        action = orch.get_initial_action()
        assert action["action"] == "MESSAGE"
        assert "text" in action
        assert "FormPilot AI" in action["text"]
        assert "describe" in action["text"].lower() or "everything" in action["text"].lower()

    def test_returns_greeting_for_incident(self, incident_schema):
        """Incident form also gets a MESSAGE greeting, not ASK_DROPDOWN."""
        mgr = FormStateManager(incident_schema)
        llm = MockLLM()
        orch = FormOrchestrator(mgr, llm)

        action = orch.get_initial_action()
        assert action["action"] == "MESSAGE"
        assert "text" in action

    def test_records_in_conversation_history(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLM()
        orch = FormOrchestrator(mgr, llm)

        orch.get_initial_action()
        history = mgr.get_conversation_history()
        assert len(history) == 1
        assert history[0]["role"] == "assistant"

    def test_all_optional_returns_form_complete(self):
        """Form with only optional fields completes immediately."""
        schema = FormSchema(
            form_id="optional",
            fields=[
                {"id": "note", "type": "text", "required": False, "prompt": "Any notes?"},
            ],
        )
        mgr = FormStateManager(schema)
        llm = MockLLM()
        orch = FormOrchestrator(mgr, llm)

        action = orch.get_initial_action()
        assert action["action"] == "FORM_COMPLETE"


# =============================================================
# Test: Happy path — extraction then sequential answers
# =============================================================


class TestHappyPath:
    """Test answering fields sequentially until form complete.

    The first process_user_message call triggers extraction (phase 1).
    Subsequent calls go through one-at-a-time (phase 2).
    """

    @pytest.mark.asyncio
    async def test_simple_form_completion_via_extraction(self, simple_schema):
        """User provides all info in first message — FORM_COMPLETE after extraction."""
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            # Extraction response — LLM extracts both fields
            {"intent": "multi_answer", "answers": {"name": "Alice", "color": "Blue"},
             "message": "I captured your name and color."},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("My name is Alice and my favorite color is Blue")
        assert result["action"] == "FORM_COMPLETE"
        assert result["data"]["name"] == "Alice"
        assert result["data"]["color"] == "Blue"

    @pytest.mark.asyncio
    async def test_partial_extraction_then_followup(self, simple_schema):
        """User provides partial info → extraction captures some, then ask remaining."""
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            # Extraction — only name extracted
            {"intent": "multi_answer", "answers": {"name": "Alice"},
             "message": "I captured your name."},
            # Follow-up phase — answer color
            {"intent": "answer", "field_id": "color", "value": "Blue", "message": "Great choice!"},
        ])
        orch = FormOrchestrator(mgr, llm)

        # First message — extraction
        result1 = await orch.process_user_message("My name is Alice")
        assert result1["action"] == "ASK_DROPDOWN"
        assert result1["field_id"] == "color"
        assert mgr.get_answer("name") == "Alice"

        # Second message — one-at-a-time
        result2 = await orch.process_user_message("Blue")
        assert result2["action"] == "FORM_COMPLETE"
        assert result2["data"]["color"] == "Blue"

    @pytest.mark.asyncio
    async def test_incident_report_full_flow(self, incident_schema):
        """Incident form: extraction + follow-up for remaining fields."""
        mgr = FormStateManager(incident_schema)
        llm = MockLLM([
            # Extraction — user mentions type and start date
            {"intent": "multi_answer",
             "answers": {"incident_type": "Accident", "start_date": "2026-02-11"},
             "message": "Captured type and start date."},
            # Follow-up: end_date
            {"intent": "answer", "field_id": "end_date", "value": "2026-02-15", "message": "Got it."},
            # followup_reason (visible because end > start)
            {"intent": "answer", "field_id": "followup_reason", "value": "Extended duration", "message": "Thanks."},
            # location
            {"intent": "answer", "field_id": "location", "value": {"lat": 24.7, "lng": 46.6}, "message": "Done."},
        ])
        orch = FormOrchestrator(mgr, llm)

        # Extraction
        r1 = await orch.process_user_message("Accident on Feb 11, 2026")
        assert r1["field_id"] == "end_date"

        r2 = await orch.process_user_message("Feb 15, 2026")
        assert r2["field_id"] == "followup_reason"

        r3 = await orch.process_user_message("Extended duration")
        assert r3["field_id"] == "location"

        r4 = await orch.process_user_message("Riyadh office")
        assert r4["action"] == "FORM_COMPLETE"
        assert len(r4["data"]) == 5


# =============================================================
# Test: Correction flow (in one-at-a-time phase)
# =============================================================


class TestCorrectionFlow:
    """Test that users can correct previously answered fields."""

    @pytest.mark.asyncio
    async def test_correction_clears_and_re_asks(self, simple_schema):
        mgr = FormStateManager(simple_schema)

        # Pre-fill name and mark extraction as done
        mgr.set_answer("name", "Alice")

        llm = MockLLM([
            {"intent": "correction", "field_id": "name", "message": "Sure, let's change your name."},
        ])
        orch = FormOrchestrator(mgr, llm)
        orch._initial_extraction_done = True  # Skip extraction phase

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
        orch._initial_extraction_done = True

        # Correction
        r1 = await orch.process_user_message("Change my name")
        assert r1["field_id"] == "name"

        # New answer
        r2 = await orch.process_user_message("Bob")
        assert mgr.get_answer("name") == "Bob"


# =============================================================
# Test: Visibility cascade (in one-at-a-time phase)
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
        orch._initial_extraction_done = True

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
        orch._initial_extraction_done = True

        result = await orch.process_user_message("Feb 10")
        # followup_reason hidden — should go to location
        assert result["field_id"] == "location"


# =============================================================
# Test: Invalid answer handling (in one-at-a-time phase)
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
        orch._initial_extraction_done = True

        result = await orch.process_user_message("Purple")
        # Should re-ask color since Purple is not a valid option
        assert result["action"] == "ASK_DROPDOWN"
        assert result["field_id"] == "color"
        assert "doesn't look right" in result["message"]

    @pytest.mark.asyncio
    async def test_answer_without_value_re_asks(self, simple_schema):
        mgr = FormStateManager(simple_schema)

        llm = MockLLM([
            # Extraction response with empty answers (nothing extracted)
            {"intent": "multi_answer", "answers": {}, "message": "I couldn't extract anything."},
            # One-at-a-time: LLM returns answer with no value
            {"intent": "answer", "field_id": "name", "value": None, "message": "Hmm"},
        ])
        orch = FormOrchestrator(mgr, llm)

        # First message triggers extraction (empty extraction)
        r1 = await orch.process_user_message("hello")
        assert r1["action"] == "ASK_TEXT"
        assert r1["field_id"] == "name"

        # Second message — one-at-a-time with no value
        result = await orch.process_user_message("hello again")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"


# =============================================================
# Test: LLM JSON failure and retry (in one-at-a-time phase)
# =============================================================


class TestLLMJsonFailure:
    """Test behavior when LLM returns invalid JSON or fails entirely."""

    @pytest.mark.asyncio
    async def test_invalid_json_then_valid_retry(self, simple_schema):
        mgr = FormStateManager(simple_schema)

        llm = MockLLMRawText([
            # Extraction phase — invalid JSON then valid retry
            "I'm not sure what you mean",
            '{"intent": "multi_answer", "answers": {}, "message": "Nothing extracted."}',
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("hello")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"
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

        # Extraction LLM fails — should fall back to asking first field
        result = await orch.process_user_message("hello")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"
        assert "trouble processing" in result["message"]

    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLMError()
        orch = FormOrchestrator(mgr, llm)

        # Extraction LLM raises — should fall back
        result = await orch.process_user_message("hello")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"

    @pytest.mark.asyncio
    async def test_json_in_markdown_fence_extracted(self, simple_schema):
        mgr = FormStateManager(simple_schema)

        llm = MockLLMRawText([
            '```json\n{"intent": "multi_answer", "answers": {"name": "Alice"}, "message": "Got it!"}\n```',
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("Alice")
        assert mgr.get_answer("name") == "Alice"

    @pytest.mark.asyncio
    async def test_one_at_a_time_llm_failure_returns_message(self, simple_schema):
        """In the one-at-a-time phase, LLM failure returns a MESSAGE fallback."""
        mgr = FormStateManager(simple_schema)
        llm = MockLLMRawText([
            # Extraction succeeds
            '{"intent": "multi_answer", "answers": {"name": "Alice"}, "message": "Got name."}',
            # One-at-a-time: all retries fail
            "not json 1",
            "not json 2",
            "not json 3",
        ])
        orch = FormOrchestrator(mgr, llm)

        # Extraction
        r1 = await orch.process_user_message("My name is Alice")
        assert r1["field_id"] == "color"

        # One-at-a-time with LLM failure
        r2 = await orch.process_user_message("hello")
        assert r2["action"] == "MESSAGE"
        assert "trouble understanding" in r2["text"]


# =============================================================
# Test: Conversation history
# =============================================================


class TestConversationHistory:
    """Test that conversation history is maintained."""

    @pytest.mark.asyncio
    async def test_messages_recorded(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {"name": "Alice"}, "message": "Got name."},
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
# Test: Clarify intent (in one-at-a-time phase)
# =============================================================


class TestClarifyIntent:
    """Test handling of clarification and unknown intents."""

    @pytest.mark.asyncio
    async def test_clarify_re_presents_field(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            # Extraction — nothing found
            {"intent": "multi_answer", "answers": {}, "message": "Nothing extracted."},
            # One-at-a-time clarify
            {"intent": "clarify", "message": "Could you please provide your name?"},
        ])
        orch = FormOrchestrator(mgr, llm)

        # Extraction
        await orch.process_user_message("asdfgh")

        # Clarify in one-at-a-time phase
        result = await orch.process_user_message("what?")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"

    @pytest.mark.asyncio
    async def test_unknown_intent_treated_as_clarify(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {}, "message": "Nothing."},
            {"intent": "unknown_thing", "message": "I'm not sure."},
        ])
        orch = FormOrchestrator(mgr, llm)

        await orch.process_user_message("gibberish")

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


# =============================================================
# Test: Multi-answer (bulk extraction) handling
# =============================================================


class TestMultiAnswer:
    """Test the bulk extraction / multi_answer handling."""

    @pytest.mark.asyncio
    async def test_multi_answer_all_valid(self, simple_schema):
        """All fields extracted in one go → FORM_COMPLETE."""
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            {"intent": "multi_answer",
             "answers": {"name": "Bob", "color": "Red"},
             "message": "All captured."},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("I'm Bob and I love Red")
        assert result["action"] == "FORM_COMPLETE"
        assert result["data"]["name"] == "Bob"
        assert result["data"]["color"] == "Red"

    @pytest.mark.asyncio
    async def test_multi_answer_partial_valid(self, simple_schema):
        """Some fields valid, some invalid → ask for remaining."""
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            {"intent": "multi_answer",
             "answers": {"name": "Bob", "color": "Purple"},  # Purple is invalid
             "message": "Got name, color seems wrong."},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("I'm Bob and I like Purple")
        assert result["action"] == "ASK_DROPDOWN"
        assert result["field_id"] == "color"
        assert mgr.get_answer("name") == "Bob"
        assert mgr.get_answer("color") is None

    @pytest.mark.asyncio
    async def test_multi_answer_empty(self, simple_schema):
        """Extraction finds nothing → ask first field."""
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {}, "message": "I couldn't extract anything."},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("I dunno")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"

    @pytest.mark.asyncio
    async def test_multi_answer_bad_format(self, simple_schema):
        """LLM returns answers as non-dict → fall back gracefully."""
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            {"intent": "multi_answer", "answers": "not a dict", "message": "Oops."},
        ])
        orch = FormOrchestrator(mgr, llm)

        result = await orch.process_user_message("test")
        assert result["action"] == "ASK_TEXT"
        assert result["field_id"] == "name"

    @pytest.mark.asyncio
    async def test_extraction_sets_initial_extraction_done(self, simple_schema):
        """After extraction, subsequent messages go to one-at-a-time phase."""
        mgr = FormStateManager(simple_schema)
        llm = MockLLM([
            {"intent": "multi_answer", "answers": {"name": "Alice"}, "message": "Got name."},
            {"intent": "answer", "field_id": "color", "value": "Green", "message": "Nice!"},
        ])
        orch = FormOrchestrator(mgr, llm)

        assert orch._initial_extraction_done is False

        await orch.process_user_message("My name is Alice")
        assert orch._initial_extraction_done is True

        # Second message should go to one-at-a-time
        result = await orch.process_user_message("Green")
        assert result["action"] == "FORM_COMPLETE"

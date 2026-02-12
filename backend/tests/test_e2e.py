"""
End-to-end tests for complete conversation flows.

Uses mock LLMs to test full multi-turn conversations from start to FORM_COMPLETE.

Tests cover:
- Full leave request flow (happy path)
- Full incident report flow with conditional visibility
- Correction flow (change a previous answer, re-evaluate)
- All-optional-fields form completes immediately
- User sends gibberish, AI clarifies
- Visibility cascade: answering a field reveals then hides conditional fields
- Multi-turn conversation history is maintained correctly
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.agent.orchestrator import FormOrchestrator
from backend.core.form_state import FormStateManager
from backend.core.schema import FormSchema

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# --- Mock LLM ---


class SequenceLLM:
    """Mock LLM that returns a predefined sequence of JSON responses."""

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        if not self.responses:
            raise RuntimeError("SequenceLLM exhausted — no more responses")
        response_dict = self.responses.pop(0)
        result = MagicMock()
        result.content = json.dumps(response_dict)
        return result


def _load_schema(name: str) -> FormSchema:
    with open(SCHEMAS_DIR / f"{name}.json") as f:
        return FormSchema(**json.load(f))


# --- E2E: Full leave request flow ---


class TestFullLeaveRequestFlow:
    """Complete leave request conversation from start to FORM_COMPLETE."""

    @pytest.mark.asyncio
    async def test_annual_leave_happy_path(self):
        """Walk through annual leave: 4 required fields → FORM_COMPLETE."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "answer", "field_id": "leave_type", "value": "Annual",
             "message": "Annual leave, got it!"},
            {"intent": "answer", "field_id": "start_date", "value": "2026-03-01",
             "message": "Start date set."},
            {"intent": "answer", "field_id": "end_date", "value": "2026-03-05",
             "message": "End date set."},
            {"intent": "answer", "field_id": "reason", "value": "Family vacation",
             "message": "Reason recorded."},
        ])

        orch = FormOrchestrator(state, llm)

        # Initial action should ask for the first field
        initial = orch.get_initial_action()
        assert initial["action"] == "ASK_DROPDOWN"
        assert initial["field_id"] == "leave_type"

        # Turn 1: leave_type
        a1 = await orch.process_user_message("I want annual leave")
        assert a1["action"] == "ASK_DATE"
        assert a1["field_id"] == "start_date"
        assert state.get_answer("leave_type") == "Annual"

        # Turn 2: start_date
        a2 = await orch.process_user_message("March 1st 2026")
        assert a2["action"] == "ASK_DATE"
        assert a2["field_id"] == "end_date"

        # Turn 3: end_date
        a3 = await orch.process_user_message("March 5th 2026")
        assert a3["action"] == "ASK_TEXT"
        assert a3["field_id"] == "reason"

        # Turn 4: reason → form complete
        a4 = await orch.process_user_message("Family vacation")
        assert a4["action"] == "FORM_COMPLETE"
        assert "data" in a4
        assert a4["data"]["leave_type"] == "Annual"
        assert a4["data"]["reason"] == "Family vacation"

        assert llm.call_count == 4

    @pytest.mark.asyncio
    async def test_sick_leave_with_conditional_field(self):
        """Sick leave triggers medical_certificate field (checkbox type)."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        # medical_certificate is a checkbox, so value must be a list
        llm = SequenceLLM([
            {"intent": "answer", "field_id": "leave_type", "value": "Sick",
             "message": "Sick leave noted."},
            {"intent": "answer", "field_id": "start_date", "value": "2026-04-01",
             "message": "Start date set."},
            {"intent": "answer", "field_id": "end_date", "value": "2026-04-03",
             "message": "End date set."},
            {"intent": "answer", "field_id": "reason", "value": "Flu",
             "message": "Reason noted."},
            {"intent": "answer", "field_id": "medical_certificate", "value": ["Yes"],
             "message": "Certificate noted."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        await orch.process_user_message("Sick leave")
        await orch.process_user_message("April 1st")
        await orch.process_user_message("April 3rd")

        # After reason, next should be medical_certificate (required, visible for Sick)
        a4 = await orch.process_user_message("Flu")
        assert a4["action"] == "ASK_CHECKBOX"
        assert a4["field_id"] == "medical_certificate"

        a5 = await orch.process_user_message("Yes")
        assert a5["action"] == "FORM_COMPLETE"
        assert a5["data"]["medical_certificate"] == ["Yes"]


# --- E2E: Full incident report flow ---


class TestFullIncidentReportFlow:
    """Incident report with conditional followup_reason field."""

    @pytest.mark.asyncio
    async def test_incident_with_followup(self):
        """End date AFTER start date → followup_reason becomes visible."""
        schema = _load_schema("incident_report")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "answer", "field_id": "incident_type", "value": "Fire",
             "message": "Fire incident."},
            {"intent": "answer", "field_id": "start_date", "value": "2026-01-10",
             "message": "Start date set."},
            {"intent": "answer", "field_id": "end_date", "value": "2026-01-15",
             "message": "End date set."},
            {"intent": "answer", "field_id": "followup_reason",
             "value": "Structural damage assessment needed",
             "message": "Followup noted."},
            {"intent": "answer", "field_id": "location",
             "value": {"lat": 24.7136, "lng": 46.6753},
             "message": "Location set."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        await orch.process_user_message("Fire")
        await orch.process_user_message("January 10")
        a3 = await orch.process_user_message("January 15")

        # followup_reason should appear because end_date > start_date
        assert a3["field_id"] == "followup_reason"

        await orch.process_user_message("Structural damage assessment needed")
        a5 = await orch.process_user_message("24.7136, 46.6753")

        assert a5["action"] == "FORM_COMPLETE"
        assert a5["data"]["followup_reason"] == "Structural damage assessment needed"

    @pytest.mark.asyncio
    async def test_incident_without_followup(self):
        """Same-day incident: end_date == start_date → followup_reason stays hidden."""
        schema = _load_schema("incident_report")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "answer", "field_id": "incident_type", "value": "Accident",
             "message": "Accident noted."},
            {"intent": "answer", "field_id": "start_date", "value": "2026-02-20",
             "message": "Start date set."},
            {"intent": "answer", "field_id": "end_date", "value": "2026-02-20",
             "message": "End date set."},
            # followup_reason should be skipped — next is location
            {"intent": "answer", "field_id": "location",
             "value": {"lat": 21.5, "lng": 39.2},
             "message": "Location set."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        await orch.process_user_message("Accident")
        await orch.process_user_message("Feb 20")
        a3 = await orch.process_user_message("Feb 20")

        # followup_reason should be skipped — same date
        assert a3["field_id"] == "location"

        a4 = await orch.process_user_message("21.5, 39.2")
        assert a4["action"] == "FORM_COMPLETE"
        assert "followup_reason" not in a4["data"]


# --- E2E: Correction flow ---


class TestCorrectionFlow:
    """Test correcting a previously answered field."""

    @pytest.mark.asyncio
    async def test_correct_leave_type_mid_conversation(self):
        """Answer leave_type as Annual, then correct to Emergency."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "answer", "field_id": "leave_type", "value": "Annual",
             "message": "Annual leave."},
            {"intent": "answer", "field_id": "start_date", "value": "2026-05-01",
             "message": "Start set."},
            # User corrects leave_type
            {"intent": "correction", "field_id": "leave_type",
             "message": "Let me change that."},
            # LLM re-asks leave_type, user says Emergency
            {"intent": "answer", "field_id": "leave_type", "value": "Emergency",
             "message": "Emergency leave."},
            {"intent": "answer", "field_id": "start_date", "value": "2026-05-01",
             "message": "Start set again."},
            {"intent": "answer", "field_id": "end_date", "value": "2026-05-02",
             "message": "End set."},
            {"intent": "answer", "field_id": "reason", "value": "Family emergency",
             "message": "Reason."},
            {"intent": "answer", "field_id": "emergency_contact",
             "value": "Ahmed 0501234567",
             "message": "Contact saved."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        await orch.process_user_message("Annual leave")
        await orch.process_user_message("May 1st")

        # Correction: clear leave_type and re-ask
        a3 = await orch.process_user_message("Actually, change leave type")
        assert a3["field_id"] == "leave_type"

        await orch.process_user_message("Emergency")

        # Now emergency_contact should become visible
        await orch.process_user_message("May 1st")
        await orch.process_user_message("May 2nd")
        await orch.process_user_message("Family emergency")

        a8 = await orch.process_user_message("Ahmed 0501234567")
        assert a8["action"] == "FORM_COMPLETE"
        assert a8["data"]["leave_type"] == "Emergency"
        assert a8["data"]["emergency_contact"] == "Ahmed 0501234567"


# --- E2E: Visibility cascade ---


class TestVisibilityCascade:
    """Changing answers causes fields to appear and disappear."""

    @pytest.mark.asyncio
    async def test_switching_leave_type_clears_conditional(self):
        """Switching from Sick to Annual clears medical_certificate answer."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "answer", "field_id": "leave_type", "value": "Sick",
             "message": "Sick leave."},
            # Now correct to Annual
            {"intent": "correction", "field_id": "leave_type",
             "message": "Changed."},
            {"intent": "answer", "field_id": "leave_type", "value": "Annual",
             "message": "Annual now."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        await orch.process_user_message("Sick leave")
        assert state.get_answer("leave_type") == "Sick"

        # Correct to Annual
        await orch.process_user_message("Change leave type")
        await orch.process_user_message("Annual")
        assert state.get_answer("leave_type") == "Annual"

        # medical_certificate should not be in visible answers
        visible = state.get_visible_answers()
        assert "medical_certificate" not in visible


# --- E2E: All optional fields ---


class TestAllOptionalFields:
    """Form with only optional fields should complete immediately."""

    @pytest.mark.asyncio
    async def test_all_optional_completes_immediately(self):
        """If all fields are optional, the form is already complete."""
        schema = FormSchema(**{
            "form_id": "optional_form",
            "fields": [
                {"id": "note1", "type": "text", "required": False,
                 "prompt": "Any notes?"},
                {"id": "note2", "type": "text", "required": False,
                 "prompt": "Additional notes?"},
            ],
        })
        state = FormStateManager(schema)
        llm = SequenceLLM([])  # Should not be called

        orch = FormOrchestrator(state, llm)

        # The form is already complete (no required fields)
        assert state.is_complete()

        # get_initial_action should return FORM_COMPLETE
        initial = orch.get_initial_action()
        assert initial["action"] == "FORM_COMPLETE"

    @pytest.mark.asyncio
    async def test_optional_fields_can_still_be_answered(self):
        """Optional fields can be answered but aren't required for completion."""
        schema = FormSchema(**{
            "form_id": "mixed_form",
            "fields": [
                {"id": "name", "type": "text", "required": True,
                 "prompt": "Your name?"},
                {"id": "nickname", "type": "text", "required": False,
                 "prompt": "Nickname?"},
            ],
        })
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "answer", "field_id": "name", "value": "Ahmed",
             "message": "Name set."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        a1 = await orch.process_user_message("Ahmed")
        # After answering the required field, form should complete
        # (optional nickname is not required)
        assert a1["action"] == "FORM_COMPLETE"


# --- E2E: Clarification ---


class TestClarificationFlow:
    """User sends gibberish or unclear messages."""

    @pytest.mark.asyncio
    async def test_gibberish_triggers_clarify(self):
        """LLM returns clarify intent for unintelligible input."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "clarify", "message": "I didn't understand. Could you "
             "please tell me the type of leave you want?"},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        a1 = await orch.process_user_message("asdfjkl;")
        # Should re-present the current field (leave_type)
        assert a1["field_id"] == "leave_type"
        assert a1["action"] == "ASK_DROPDOWN"
        # No answer should have been stored
        assert state.get_answer("leave_type") is None

    @pytest.mark.asyncio
    async def test_ask_intent_shows_info(self):
        """User asks a question instead of answering."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "ask", "message": "Sick leave requires a medical "
             "certificate. Annual leave does not."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        a1 = await orch.process_user_message("What's the difference between sick and annual?")
        # Should re-present the current field with the info message
        assert a1["field_id"] == "leave_type"


# --- E2E: Conversation history ---


class TestConversationHistory:
    """Verify conversation history is maintained across turns."""

    @pytest.mark.asyncio
    async def test_history_grows_with_each_turn(self):
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "answer", "field_id": "leave_type", "value": "Annual",
             "message": "Annual leave."},
            {"intent": "answer", "field_id": "start_date", "value": "2026-06-01",
             "message": "Start date set."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        # After initial action: 1 entry (AI greeting)
        assert len(state.get_conversation_history()) == 1

        await orch.process_user_message("Annual leave")
        # User message + AI response = 3 total
        assert len(state.get_conversation_history()) == 3

        await orch.process_user_message("June 1st")
        # +2 more = 5 total
        assert len(state.get_conversation_history()) == 5

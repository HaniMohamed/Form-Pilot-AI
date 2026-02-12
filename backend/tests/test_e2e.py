"""
End-to-end tests for complete conversation flows.

Uses mock LLMs to test full multi-turn conversations from start to FORM_COMPLETE.
Tests account for the two-phase flow:
1. Greeting (MESSAGE) → User describes data → Bulk extraction (multi_answer)
2. Follow-up: one-at-a-time for remaining missing fields

Tests cover:
- Full leave request flow (happy path with extraction + follow-up)
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
        """User provides leave type in description → extraction → follow-up for the rest."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            # Extraction: user mentions annual leave + start date
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual", "start_date": "2026-03-01"},
             "message": "I captured your leave type and start date."},
            # Follow-up: end_date
            {"intent": "answer", "field_id": "end_date", "value": "2026-03-05",
             "message": "End date set."},
            # Follow-up: reason
            {"intent": "answer", "field_id": "reason", "value": "Family vacation",
             "message": "Reason recorded."},
        ])

        orch = FormOrchestrator(state, llm)

        # Initial action should be a greeting MESSAGE
        initial = orch.get_initial_action()
        assert initial["action"] == "MESSAGE"
        assert "text" in initial

        # Turn 1: Extraction — user provides description
        a1 = await orch.process_user_message("I want annual leave starting March 1st 2026")
        assert a1["action"] == "ASK_DATE"
        assert a1["field_id"] == "end_date"
        assert state.get_answer("leave_type") == "Annual"
        assert state.get_answer("start_date") == "2026-03-01"

        # Turn 2: end_date
        a2 = await orch.process_user_message("March 5th 2026")
        assert a2["action"] == "ASK_TEXT"
        assert a2["field_id"] == "reason"

        # Turn 3: reason → form complete
        a3 = await orch.process_user_message("Family vacation")
        assert a3["action"] == "FORM_COMPLETE"
        assert "data" in a3
        assert a3["data"]["leave_type"] == "Annual"
        assert a3["data"]["reason"] == "Family vacation"

        assert llm.call_count == 3

    @pytest.mark.asyncio
    async def test_sick_leave_with_conditional_field(self):
        """Sick leave triggers medical_certificate field (checkbox type)."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        # medical_certificate is a checkbox, so value must be a list
        llm = SequenceLLM([
            # Extraction: leave type + dates + reason extracted
            {"intent": "multi_answer",
             "answers": {"leave_type": "Sick", "start_date": "2026-04-01",
                         "end_date": "2026-04-03", "reason": "Flu"},
             "message": "Captured leave details."},
            # Follow-up: medical_certificate (now visible because Sick)
            {"intent": "answer", "field_id": "medical_certificate", "value": ["Yes"],
             "message": "Certificate noted."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        # Extraction — captures most fields, but medical_certificate is still needed
        a1 = await orch.process_user_message("Sick leave from April 1st to 3rd, reason is Flu")
        assert a1["action"] == "ASK_CHECKBOX"
        assert a1["field_id"] == "medical_certificate"

        # Answer medical_certificate → form complete
        a2 = await orch.process_user_message("Yes")
        assert a2["action"] == "FORM_COMPLETE"
        assert a2["data"]["medical_certificate"] == ["Yes"]

    @pytest.mark.asyncio
    async def test_all_fields_in_extraction(self):
        """User provides everything in one message — FORM_COMPLETE after extraction."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {
                 "leave_type": "Annual",
                 "start_date": "2026-05-01",
                 "end_date": "2026-05-10",
                 "reason": "Holiday trip",
             },
             "message": "All fields captured!"},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        result = await orch.process_user_message(
            "Annual leave from May 1st to May 10th for a holiday trip"
        )
        assert result["action"] == "FORM_COMPLETE"
        assert result["data"]["leave_type"] == "Annual"
        assert result["data"]["end_date"] == "2026-05-10"


# --- E2E: Full incident report flow ---


class TestFullIncidentReportFlow:
    """Incident report with conditional followup_reason field."""

    @pytest.mark.asyncio
    async def test_incident_with_followup(self):
        """End date AFTER start date → followup_reason becomes visible."""
        schema = _load_schema("incident_report")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            # Extraction: type + start + end extracted
            {"intent": "multi_answer",
             "answers": {"incident_type": "Fire", "start_date": "2026-01-10",
                         "end_date": "2026-01-15"},
             "message": "Captured incident details."},
            # Follow-up: followup_reason (visible because end > start)
            {"intent": "answer", "field_id": "followup_reason",
             "value": "Structural damage assessment needed",
             "message": "Followup noted."},
            # Follow-up: location
            {"intent": "answer", "field_id": "location",
             "value": {"lat": 24.7136, "lng": 46.6753},
             "message": "Location set."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        # Extraction
        a1 = await orch.process_user_message("Fire incident from Jan 10 to Jan 15")
        # followup_reason should appear because end_date > start_date
        assert a1["field_id"] == "followup_reason"

        a2 = await orch.process_user_message("Structural damage assessment needed")
        assert a2["field_id"] == "location"

        a3 = await orch.process_user_message("24.7136, 46.6753")
        assert a3["action"] == "FORM_COMPLETE"
        assert a3["data"]["followup_reason"] == "Structural damage assessment needed"

    @pytest.mark.asyncio
    async def test_incident_without_followup(self):
        """Same-day incident: end_date == start_date → followup_reason stays hidden."""
        schema = _load_schema("incident_report")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            # Extraction: same-day incident
            {"intent": "multi_answer",
             "answers": {"incident_type": "Accident", "start_date": "2026-02-20",
                         "end_date": "2026-02-20"},
             "message": "Captured details."},
            # Follow-up: location (followup_reason skipped)
            {"intent": "answer", "field_id": "location",
             "value": {"lat": 21.5, "lng": 39.2},
             "message": "Location set."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        a1 = await orch.process_user_message("Accident on Feb 20")
        # followup_reason should be skipped — same date
        assert a1["field_id"] == "location"

        a2 = await orch.process_user_message("21.5, 39.2")
        assert a2["action"] == "FORM_COMPLETE"
        assert "followup_reason" not in a2["data"]


# --- E2E: Correction flow ---


class TestCorrectionFlow:
    """Test correcting a previously answered field."""

    @pytest.mark.asyncio
    async def test_correct_leave_type_mid_conversation(self):
        """Answer leave_type via extraction, then correct to Emergency in follow-up."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            # Extraction: Annual leave + start date
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual", "start_date": "2026-05-01"},
             "message": "Got leave type and start."},
            # User corrects leave_type
            {"intent": "correction", "field_id": "leave_type",
             "message": "Let me change that."},
            # Re-asks leave_type, user says Emergency
            {"intent": "answer", "field_id": "leave_type", "value": "Emergency",
             "message": "Emergency leave."},
            # Continue with remaining fields
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

        # Extraction
        a1 = await orch.process_user_message("Annual leave from May 1st")
        assert a1["field_id"] == "end_date"

        # Correction
        a2 = await orch.process_user_message("Actually, change leave type")
        assert a2["field_id"] == "leave_type"

        # Answer Emergency
        await orch.process_user_message("Emergency")

        # Now emergency_contact should become visible
        await orch.process_user_message("May 1st")
        await orch.process_user_message("May 2nd")
        await orch.process_user_message("Family emergency")

        a_final = await orch.process_user_message("Ahmed 0501234567")
        assert a_final["action"] == "FORM_COMPLETE"
        assert a_final["data"]["leave_type"] == "Emergency"
        assert a_final["data"]["emergency_contact"] == "Ahmed 0501234567"


# --- E2E: Visibility cascade ---


class TestVisibilityCascade:
    """Changing answers causes fields to appear and disappear."""

    @pytest.mark.asyncio
    async def test_switching_leave_type_clears_conditional(self):
        """Switching from Sick to Annual clears medical_certificate answer."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            # Extraction: Sick leave
            {"intent": "multi_answer",
             "answers": {"leave_type": "Sick"},
             "message": "Sick leave."},
            # Correction: change to Annual
            {"intent": "correction", "field_id": "leave_type",
             "message": "Changed."},
            {"intent": "answer", "field_id": "leave_type", "value": "Annual",
             "message": "Annual now."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        # Extraction
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
            # Extraction: captures name
            {"intent": "multi_answer",
             "answers": {"name": "Ahmed"},
             "message": "Name set."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        a1 = await orch.process_user_message("Ahmed")
        # After answering the required field via extraction, form should complete
        assert a1["action"] == "FORM_COMPLETE"


# --- E2E: Clarification ---


class TestClarificationFlow:
    """User sends gibberish or unclear messages."""

    @pytest.mark.asyncio
    async def test_gibberish_triggers_clarify(self):
        """LLM returns empty extraction, then clarify in follow-up."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            # Extraction: nothing found
            {"intent": "multi_answer", "answers": {},
             "message": "I couldn't understand. Please provide your leave details."},
            # One-at-a-time: clarify
            {"intent": "clarify", "message": "I didn't understand. Could you "
             "please tell me the type of leave you want?"},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        # Extraction — nothing found, asks first field
        a1 = await orch.process_user_message("asdfjkl;")
        assert a1["field_id"] == "leave_type"
        assert a1["action"] == "ASK_DROPDOWN"

        # Follow-up clarify
        a2 = await orch.process_user_message("asdfjkl; again")
        assert a2["field_id"] == "leave_type"
        assert state.get_answer("leave_type") is None

    @pytest.mark.asyncio
    async def test_ask_intent_shows_info(self):
        """User asks a question instead of answering."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            # Extraction: nothing useful
            {"intent": "multi_answer", "answers": {},
             "message": "No data found."},
            # Follow-up: ask intent
            {"intent": "ask", "message": "Sick leave requires a medical "
             "certificate. Annual leave does not."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        await orch.process_user_message("tell me about leave types")
        a2 = await orch.process_user_message("What's the difference between sick and annual?")
        assert a2["field_id"] == "leave_type"


# --- E2E: Conversation history ---


class TestConversationHistory:
    """Verify conversation history is maintained across turns."""

    @pytest.mark.asyncio
    async def test_history_grows_with_each_turn(self):
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            # Extraction
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual"},
             "message": "Annual leave captured."},
            # Follow-up
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

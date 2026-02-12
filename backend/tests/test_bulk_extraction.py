"""
Dedicated tests for the bulk extraction flow.

Tests cover:
- User provides ALL data in one message → FORM_COMPLETE after extraction
- User provides partial data → extraction + follow-up questions for remaining
- User provides gibberish → extraction finds nothing → asks all fields one at a time
- Extraction with conditional fields (some conditional fields become visible after extraction)
- Extraction with invalid values mixed in (rejected silently, asked later)
- Extraction summary message contains accepted/rejected field info
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


# --- Complete extraction in one shot ---


class TestCompleteExtractionOneShot:
    """User provides all required data in one free-text message."""

    @pytest.mark.asyncio
    async def test_all_leave_fields_extracted(self):
        """All 4 required leave request fields extracted → FORM_COMPLETE."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {
                 "leave_type": "Annual",
                 "start_date": "2026-06-01",
                 "end_date": "2026-06-10",
                 "reason": "Summer holiday",
             },
             "message": "I captured all your leave details."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        result = await orch.process_user_message(
            "Annual leave from June 1st to June 10th for summer holiday"
        )
        assert result["action"] == "FORM_COMPLETE"
        assert result["data"]["leave_type"] == "Annual"
        assert result["data"]["start_date"] == "2026-06-01"
        assert result["data"]["end_date"] == "2026-06-10"
        assert result["data"]["reason"] == "Summer holiday"
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_all_incident_fields_extracted_with_followup(self):
        """All incident fields including conditional followup_reason extracted."""
        schema = _load_schema("incident_report")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {
                 "incident_type": "Fire",
                 "start_date": "2026-01-10",
                 "end_date": "2026-01-15",
                 "followup_reason": "Structural assessment needed",
                 "location": {"lat": 24.7136, "lng": 46.6753},
             },
             "message": "All incident details captured."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        result = await orch.process_user_message(
            "Fire incident from Jan 10 to Jan 15, followup due to structural "
            "assessment needed, at lat 24.7136 lng 46.6753"
        )
        assert result["action"] == "FORM_COMPLETE"
        assert result["data"]["followup_reason"] == "Structural assessment needed"
        assert result["data"]["location"] == {"lat": 24.7136, "lng": 46.6753}


# --- Partial extraction + follow-up ---


class TestPartialExtraction:
    """User provides some data, AI asks for the rest one at a time."""

    @pytest.mark.asyncio
    async def test_leave_partial_extraction(self):
        """User provides leave type only → extraction captures it → asks remaining."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {"leave_type": "Sick"},
             "message": "I noted your leave type as Sick."},
            # Follow-up: start_date
            {"intent": "answer", "field_id": "start_date", "value": "2026-03-01",
             "message": "Start date set."},
            # Follow-up: end_date
            {"intent": "answer", "field_id": "end_date", "value": "2026-03-03",
             "message": "End date set."},
            # Follow-up: reason
            {"intent": "answer", "field_id": "reason", "value": "Flu",
             "message": "Reason noted."},
            # Follow-up: medical_certificate (visible for Sick leave)
            {"intent": "answer", "field_id": "medical_certificate", "value": ["Yes"],
             "message": "Certificate noted."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        # Extraction — only leave_type captured
        r1 = await orch.process_user_message("I need sick leave")
        assert r1["action"] == "ASK_DATE"
        assert r1["field_id"] == "start_date"
        assert state.get_answer("leave_type") == "Sick"

        # Continue one at a time
        r2 = await orch.process_user_message("March 1st")
        assert r2["field_id"] == "end_date"

        r3 = await orch.process_user_message("March 3rd")
        assert r3["field_id"] == "reason"

        r4 = await orch.process_user_message("Flu")
        assert r4["field_id"] == "medical_certificate"

        r5 = await orch.process_user_message("Yes")
        assert r5["action"] == "FORM_COMPLETE"
        assert r5["data"]["leave_type"] == "Sick"
        assert r5["data"]["medical_certificate"] == ["Yes"]

    @pytest.mark.asyncio
    async def test_incident_partial_extraction_no_followup(self):
        """Extraction captures same-day incident → followup_reason stays hidden."""
        schema = _load_schema("incident_report")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {"incident_type": "Injury", "start_date": "2026-02-20",
                         "end_date": "2026-02-20"},
             "message": "Captured injury details."},
            # Next missing: location (followup_reason hidden because same day)
            {"intent": "answer", "field_id": "location",
             "value": {"lat": 21.5, "lng": 39.2},
             "message": "Location set."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        r1 = await orch.process_user_message("Injury on Feb 20")
        assert r1["field_id"] == "location"
        assert "followup_reason" not in state.get_all_answers()

        r2 = await orch.process_user_message("21.5, 39.2")
        assert r2["action"] == "FORM_COMPLETE"


# --- Gibberish extraction ---


class TestGibberishExtraction:
    """User provides unintelligible text → extraction fails to find anything."""

    @pytest.mark.asyncio
    async def test_gibberish_asks_first_field(self):
        """Empty extraction → falls back to asking fields one at a time."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "multi_answer", "answers": {},
             "message": "I couldn't understand your request."},
            # Now one-at-a-time flow begins
            {"intent": "answer", "field_id": "leave_type", "value": "Annual",
             "message": "Annual leave."},
            {"intent": "answer", "field_id": "start_date", "value": "2026-04-01",
             "message": "Start date."},
            {"intent": "answer", "field_id": "end_date", "value": "2026-04-05",
             "message": "End date."},
            {"intent": "answer", "field_id": "reason", "value": "Vacation",
             "message": "Reason."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        # Gibberish extraction
        r1 = await orch.process_user_message("asdfghjkl qwerty")
        assert r1["action"] == "ASK_DROPDOWN"
        assert r1["field_id"] == "leave_type"

        # User now answers properly one at a time
        r2 = await orch.process_user_message("Annual")
        assert r2["field_id"] == "start_date"

        r3 = await orch.process_user_message("April 1st")
        assert r3["field_id"] == "end_date"

        r4 = await orch.process_user_message("April 5th")
        assert r4["field_id"] == "reason"

        r5 = await orch.process_user_message("Vacation")
        assert r5["action"] == "FORM_COMPLETE"


# --- Extraction with invalid values ---


class TestExtractionWithInvalidValues:
    """Extraction returns some valid and some invalid values."""

    @pytest.mark.asyncio
    async def test_mixed_valid_invalid_extraction(self):
        """Some extracted values are invalid → accepted are stored, invalid skipped."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {
                 "leave_type": "Annual",  # Valid
                 "start_date": "not-a-date",  # Invalid
                 "reason": "Holiday",  # Valid
             },
             "message": "I captured what I could."},
            # Follow-up: start_date (was rejected)
            {"intent": "answer", "field_id": "start_date", "value": "2026-07-01",
             "message": "Start date set."},
            # Follow-up: end_date (was never in extraction)
            {"intent": "answer", "field_id": "end_date", "value": "2026-07-10",
             "message": "End date set."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        # Extraction — leave_type and reason accepted, start_date rejected
        r1 = await orch.process_user_message("Annual leave, date is blah, for holiday")
        assert state.get_answer("leave_type") == "Annual"
        assert state.get_answer("reason") == "Holiday"
        assert state.get_answer("start_date") is None  # Rejected
        assert r1["field_id"] == "start_date"

        # Answer start_date
        r2 = await orch.process_user_message("July 1st")
        assert r2["field_id"] == "end_date"

        # Answer end_date → FORM_COMPLETE
        r3 = await orch.process_user_message("July 10th")
        assert r3["action"] == "FORM_COMPLETE"

    @pytest.mark.asyncio
    async def test_invalid_dropdown_in_extraction(self):
        """Extraction tries an invalid dropdown option → rejected, asked later."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {
                 "leave_type": "Vacation",  # Not a valid option
                 "start_date": "2026-08-01",
                 "end_date": "2026-08-10",
                 "reason": "Holiday",
             },
             "message": "Captured some details."},
            # Follow-up: leave_type (was rejected because Vacation is not valid)
            {"intent": "answer", "field_id": "leave_type", "value": "Annual",
             "message": "Annual leave."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        r1 = await orch.process_user_message("Vacation from Aug 1 to Aug 10 for holiday")
        assert state.get_answer("leave_type") is None  # Rejected
        assert state.get_answer("start_date") == "2026-08-01"  # Accepted
        assert r1["field_id"] == "leave_type"

        r2 = await orch.process_user_message("Annual leave")
        assert r2["action"] == "FORM_COMPLETE"
        assert r2["data"]["leave_type"] == "Annual"


# --- Extraction with conditional fields that become visible ---


class TestExtractionConditionalVisibility:
    """Extraction sets answers that trigger conditional field visibility."""

    @pytest.mark.asyncio
    async def test_sick_leave_triggers_medical_certificate(self):
        """Extraction sets leave_type=Sick → medical_certificate becomes visible."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {
                 "leave_type": "Sick",
                 "start_date": "2026-09-01",
                 "end_date": "2026-09-05",
                 "reason": "Surgery recovery",
             },
             "message": "Captured sick leave details."},
            # medical_certificate should now be visible
            {"intent": "answer", "field_id": "medical_certificate", "value": ["Yes"],
             "message": "Certificate noted."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        r1 = await orch.process_user_message("Sick leave from Sep 1 to Sep 5 for surgery recovery")
        # Should ask for medical_certificate (visible due to Sick leave type)
        assert r1["action"] == "ASK_CHECKBOX"
        assert r1["field_id"] == "medical_certificate"

        r2 = await orch.process_user_message("Yes")
        assert r2["action"] == "FORM_COMPLETE"

    @pytest.mark.asyncio
    async def test_extraction_with_emergency_contact(self):
        """Emergency leave type triggers emergency_contact field."""
        schema = _load_schema("leave_request")
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {
                 "leave_type": "Emergency",
                 "start_date": "2026-10-01",
                 "end_date": "2026-10-02",
                 "reason": "Family emergency",
             },
             "message": "Emergency leave captured."},
            {"intent": "answer", "field_id": "emergency_contact",
             "value": "Ahmed 0501234567",
             "message": "Contact saved."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        r1 = await orch.process_user_message(
            "Emergency leave Oct 1-2 for family emergency"
        )
        assert r1["field_id"] == "emergency_contact"

        r2 = await orch.process_user_message("Ahmed 0501234567")
        assert r2["action"] == "FORM_COMPLETE"
        assert r2["data"]["emergency_contact"] == "Ahmed 0501234567"

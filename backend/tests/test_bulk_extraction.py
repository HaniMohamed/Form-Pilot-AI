"""
Dedicated tests for the bulk extraction flow in the markdown-driven orchestrator.

Tests cover:
- User provides ALL data in one message → answers extracted
- User provides partial data → extraction captures some, conversation continues
- User provides gibberish → extraction finds nothing
- Extraction with non-dict answers → handled gracefully
"""

import json
from unittest.mock import MagicMock

import pytest

from backend.agent.orchestrator import FormOrchestrator


LEAVE_FORM_MD = """
# Leave Request Form

## Fields
- **leave_type** (dropdown, required): Type of leave?
  Options: Annual, Sick, Emergency
- **start_date** (date, required): Start date?
- **end_date** (date, required): End date?
- **reason** (text, required): Reason for leave?
"""


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


# --- Complete extraction in one shot ---


class TestCompleteExtractionOneShot:
    """User provides all required data in one free-text message."""

    @pytest.mark.asyncio
    async def test_all_fields_extracted(self):
        """All leave fields extracted → stored in answers."""
        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {
                 "leave_type": "Annual",
                 "start_date": "2026-06-01",
                 "end_date": "2026-06-10",
                 "reason": "Summer holiday",
             },
             "message": "I captured all your leave details."},
            # Conversation phase: FORM_COMPLETE
            {"action": "FORM_COMPLETE",
             "data": {"leave_type": "Annual", "start_date": "2026-06-01",
                      "end_date": "2026-06-10", "reason": "Summer holiday"},
             "message": "Form complete!"},
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        result = await orch.process_user_message(
            "Annual leave from June 1st to June 10th for summer holiday"
        )
        assert result["action"] == "FORM_COMPLETE"
        assert orch.answers["leave_type"] == "Annual"
        assert orch.answers["reason"] == "Summer holiday"


# --- Partial extraction + follow-up ---


class TestPartialExtraction:
    """User provides some data, AI asks for the rest one at a time."""

    @pytest.mark.asyncio
    async def test_partial_extraction(self):
        """User provides leave type only → extraction captures it → asks remaining."""
        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {"leave_type": "Sick"},
             "message": "I noted your leave type as Sick."},
            # Conversation: ask start_date
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start date?",
             "message": "When does your leave start?"},
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        result = await orch.process_user_message("I need sick leave")
        assert result["action"] == "ASK_DATE"
        assert result["field_id"] == "start_date"
        assert orch.answers.get("leave_type") == "Sick"


# --- Gibberish extraction ---


class TestGibberishExtraction:
    """User provides unintelligible text → extraction fails to find anything."""

    @pytest.mark.asyncio
    async def test_gibberish_asks_first_field(self):
        """Empty extraction → falls back to asking fields one at a time."""
        llm = SequenceLLM([
            {"intent": "multi_answer", "answers": {},
             "message": "I couldn't understand your request."},
            # Conversation: ask first field
            {"action": "ASK_DROPDOWN", "field_id": "leave_type",
             "label": "Type of leave?",
             "options": ["Annual", "Sick", "Emergency"],
             "message": "What type of leave do you need?"},
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        result = await orch.process_user_message("asdfghjkl qwerty")
        assert result["action"] == "ASK_DROPDOWN"
        assert result["field_id"] == "leave_type"


# --- Extraction with non-dict answers ---


class TestExtractionBadFormat:
    """Extraction returns answers in unexpected format."""

    @pytest.mark.asyncio
    async def test_non_dict_answers_handled(self):
        """LLM returns answers as non-dict → falls through to conversation."""
        llm = SequenceLLM([
            {"intent": "multi_answer", "answers": "not a dict",
             "message": "Oops."},
            # Conversation continues
            {"action": "ASK_DROPDOWN", "field_id": "leave_type",
             "label": "Type?",
             "options": ["Annual", "Sick", "Emergency"],
             "message": "What type of leave?"},
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        result = await orch.process_user_message("test")
        assert result["action"] == "ASK_DROPDOWN"
        assert result["field_id"] == "leave_type"

    @pytest.mark.asyncio
    async def test_extraction_sets_done_flag(self):
        """After extraction (even empty), flag is set and second message goes to conversation."""
        llm = SequenceLLM([
            {"intent": "multi_answer", "answers": {"leave_type": "Annual"},
             "message": "Got leave type."},
            # Conversation: ask next field
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start?", "message": "When?"},
            # Second message: conversation continues
            {"action": "ASK_DATE", "field_id": "end_date",
             "label": "End?", "message": "When does it end?"},
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        assert orch._initial_extraction_done is False

        await orch.process_user_message("Annual leave")
        assert orch._initial_extraction_done is True

        # Second message goes to conversation, not extraction
        result = await orch.process_user_message("March 1st")
        assert result["action"] == "ASK_DATE"

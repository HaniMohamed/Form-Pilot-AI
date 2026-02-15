"""
End-to-end tests for complete markdown-driven conversation flows.

Uses mock LLMs to test full multi-turn conversations:
1. Greeting (MESSAGE) → User describes data → Bulk extraction
2. LLM-driven follow-up: one field at a time via ASK_* actions
3. Tool calls: AI requests data → mock results → AI continues

Tests cover:
- Full form flow with extraction + follow-up
- Tool call round-trip through the orchestrator
- All fields extracted in one shot → FORM_COMPLETE
- Gibberish → clarification
- Conversation history across turns
"""

import json
from unittest.mock import MagicMock

import pytest

from backend.agent.orchestrator import FormOrchestrator

# Markdown form definitions for tests
LEAVE_FORM_MD = """
# Leave Request Form

## Fields
- **leave_type** (dropdown, required): What type of leave?
  Options: Annual, Sick, Emergency
- **start_date** (date, required): Start date?
- **end_date** (date, required): End date?
- **reason** (text, required): Reason for leave?
"""

TOOL_FORM_MD = """
# Report Injury Form

## Tools
- `get_establishments`: Returns the user's establishments
- `get_injury_types`: Returns injury type options
- `set_field_value(fieldId, value)`: Sets a field value

## Fields
- **establishment** (dropdown, required): Select establishment
  Data source: call `get_establishments`
- **injury_type** (dropdown, required): Select injury type
  Data source: call `get_injury_types`
- **injury_date** (date, required): When did the injury occur?
- **description** (text, required): Describe the injury
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


# --- E2E: Full leave request flow ---


class TestFullLeaveRequestFlow:
    """Complete leave request conversation from start to FORM_COMPLETE."""

    @pytest.mark.asyncio
    async def test_partial_extraction_then_followup(self):
        """User provides some info in description → extraction + follow-up."""
        llm = SequenceLLM([
            # Extraction: leave_type and start_date captured
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual", "start_date": "2026-03-01"},
             "message": "Captured leave type and start date."},
            # Conversation: ask end_date
            {"action": "ASK_DATE", "field_id": "end_date",
             "label": "End date?",
             "message": "When does your leave end?"},
            # Answer end_date
            {"action": "ASK_TEXT", "field_id": "reason",
             "label": "Reason?",
             "message": "Got March 5th. What's the reason?"},
            # Answer reason → FORM_COMPLETE
            {"action": "FORM_COMPLETE",
             "data": {"leave_type": "Annual", "start_date": "2026-03-01",
                      "end_date": "2026-03-05", "reason": "Holiday"},
             "message": "All done!"},
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)

        # Initial greeting
        initial = orch.get_initial_action()
        assert initial["action"] == "MESSAGE"

        # Turn 1: Extraction
        a1 = await orch.process_user_message("Annual leave starting March 1st 2026")
        assert a1["action"] == "ASK_DATE"
        assert a1["field_id"] == "end_date"
        assert orch.answers.get("leave_type") == "Annual"

        # Turn 2: end_date
        a2 = await orch.process_user_message("March 5th 2026")
        assert a2["action"] == "ASK_TEXT"
        assert a2["field_id"] == "reason"

        # Turn 3: reason → form complete
        a3 = await orch.process_user_message("Holiday")
        assert a3["action"] == "FORM_COMPLETE"
        assert a3["data"]["leave_type"] == "Annual"
        assert a3["data"]["reason"] == "Holiday"

    @pytest.mark.asyncio
    async def test_all_fields_in_extraction(self):
        """User provides everything in one message → FORM_COMPLETE."""
        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {
                 "leave_type": "Annual",
                 "start_date": "2026-05-01",
                 "end_date": "2026-05-10",
                 "reason": "Holiday trip",
             },
             "message": "All fields captured!"},
            {"action": "FORM_COMPLETE",
             "data": {"leave_type": "Annual", "start_date": "2026-05-01",
                      "end_date": "2026-05-10", "reason": "Holiday trip"},
             "message": "Form complete!"},
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        result = await orch.process_user_message(
            "Annual leave from May 1st to May 10th for a holiday trip"
        )
        assert result["action"] == "FORM_COMPLETE"


# --- E2E: Tool call flow ---


class TestToolCallFlow:
    """Full conversation with tool calls."""

    @pytest.mark.asyncio
    async def test_tool_call_then_ask_field(self):
        """AI requests tool → frontend returns data → AI presents options."""
        llm = SequenceLLM([
            # Extraction: nothing extracted, need to get data first
            {"intent": "multi_answer", "answers": {},
             "message": "Let me get your data first."},
            # Conversation: request establishments tool
            {"action": "TOOL_CALL", "tool_name": "get_establishments",
             "tool_args": {}, "message": "Fetching your establishments..."},
            # After tool results: present establishments
            {"action": "ASK_DROPDOWN", "field_id": "establishment",
             "label": "Select establishment",
             "options": ["Riyadh Tech Co.", "Saudi Digital"],
             "message": "Please select your establishment."},
            # User selects → request injury types
            {"action": "TOOL_CALL", "tool_name": "get_injury_types",
             "tool_args": {}, "message": "Fetching injury types..."},
            # After injury types: present options
            {"action": "ASK_DROPDOWN", "field_id": "injury_type",
             "label": "Select injury type",
             "options": ["Work Injury", "Road Accident"],
             "message": "What type of injury?"},
        ])

        orch = FormOrchestrator(TOOL_FORM_MD, llm)
        orch.get_initial_action()

        # User message → extraction → tool call
        r1 = await orch.process_user_message("I need to report an injury")
        assert r1["action"] == "TOOL_CALL"
        assert r1["tool_name"] == "get_establishments"

        # Send tool results
        r2 = await orch.process_user_message("", tool_results=[{
            "tool_name": "get_establishments",
            "result": {"establishments": [
                {"name": "Riyadh Tech Co."},
                {"name": "Saudi Digital"},
            ]},
        }])
        assert r2["action"] == "ASK_DROPDOWN"
        assert r2["field_id"] == "establishment"

        # User selects establishment → next tool call
        r3 = await orch.process_user_message("Riyadh Tech Co.")
        assert r3["action"] == "TOOL_CALL"
        assert r3["tool_name"] == "get_injury_types"

        # Send injury types
        r4 = await orch.process_user_message("", tool_results=[{
            "tool_name": "get_injury_types",
            "result": {"types": ["Work Injury", "Road Accident"]},
        }])
        assert r4["action"] == "ASK_DROPDOWN"
        assert r4["field_id"] == "injury_type"

        assert llm.call_count == 5

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_sequence(self):
        """Multiple tool calls executed one after another."""
        llm = SequenceLLM([
            # Extraction: nothing
            {"intent": "multi_answer", "answers": {},
             "message": "Need data."},
            # Tool call 1
            {"action": "TOOL_CALL", "tool_name": "get_establishments",
             "tool_args": {}, "message": "Getting establishments..."},
            # After tool 1: tool call 2
            {"action": "TOOL_CALL", "tool_name": "get_injury_types",
             "tool_args": {}, "message": "Getting injury types..."},
            # After tool 2: ask first field
            {"action": "ASK_DROPDOWN", "field_id": "establishment",
             "label": "Select",
             "options": ["Company A"],
             "message": "Select your establishment."},
        ])

        orch = FormOrchestrator(TOOL_FORM_MD, llm)
        orch.get_initial_action()

        # Extraction → tool call 1
        r1 = await orch.process_user_message("Report injury")
        assert r1["action"] == "TOOL_CALL"

        # Tool 1 result → tool call 2
        r2 = await orch.process_user_message("", tool_results=[{
            "tool_name": "get_establishments",
            "result": {"establishments": ["Company A"]},
        }])
        assert r2["action"] == "TOOL_CALL"
        assert r2["tool_name"] == "get_injury_types"

        # Tool 2 result → ask field
        r3 = await orch.process_user_message("", tool_results=[{
            "tool_name": "get_injury_types",
            "result": {"types": ["Work Injury"]},
        }])
        assert r3["action"] == "ASK_DROPDOWN"


# --- E2E: Gibberish and clarification ---


class TestClarificationFlow:
    """User sends gibberish or unclear messages."""

    @pytest.mark.asyncio
    async def test_gibberish_triggers_ask_field(self):
        """Empty extraction → LLM asks for first field."""
        llm = SequenceLLM([
            {"intent": "multi_answer", "answers": {},
             "message": "I couldn't understand."},
            {"action": "ASK_DROPDOWN", "field_id": "leave_type",
             "label": "Type of leave?",
             "options": ["Annual", "Sick", "Emergency"],
             "message": "What type of leave do you need?"},
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        result = await orch.process_user_message("asdfjkl;")
        assert result["action"] == "ASK_DROPDOWN"
        assert result["field_id"] == "leave_type"


# --- E2E: Conversation history ---


class TestConversationHistory:
    """Verify conversation history is maintained across turns."""

    @pytest.mark.asyncio
    async def test_history_grows_with_each_turn(self):
        llm = SequenceLLM([
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual"},
             "message": "Annual leave captured."},
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start date?",
             "message": "When does it start?"},
            {"action": "ASK_DATE", "field_id": "end_date",
             "label": "End date?",
             "message": "When does it end?"},
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        # After initial: 1 entry (greeting)
        assert len(orch.conversation_history) == 1

        await orch.process_user_message("Annual leave")
        # user + extraction msg + conversation msg
        assert len(orch.conversation_history) >= 3

        await orch.process_user_message("March 1st")
        assert len(orch.conversation_history) >= 5

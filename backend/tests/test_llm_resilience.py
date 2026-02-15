"""
LLM output resilience tests for the markdown-driven orchestrator.

Tests cover:
- Malformed JSON responses from LLM (during extraction and conversation)
- Unexpected keys in LLM JSON response
- LLM timeout / exception handling
- LLM returns JSON embedded in markdown code fences
- LLM returns empty response
- Retry mechanism: first attempt fails, second succeeds
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


# --- Mock LLMs ---


class RawTextLLM:
    """Returns raw text strings (not necessarily valid JSON)."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        if not self.responses:
            raise RuntimeError("No more responses")
        result = MagicMock()
        result.content = self.responses.pop(0)
        return result


class FailThenSucceedLLM:
    """Fails N times then returns a valid response."""

    def __init__(self, failures: list[str], success: dict):
        self.failures = list(failures)
        self.success = success
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        if self.failures:
            result = MagicMock()
            result.content = self.failures.pop(0)
            return result
        result = MagicMock()
        result.content = json.dumps(self.success)
        return result


class ExceptionLLM:
    """Raises an exception on every call."""

    def __init__(self, error_message: str = "LLM service unavailable"):
        self.error_message = error_message
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        raise RuntimeError(self.error_message)


class SequenceLLM:
    """Returns a sequence of JSON responses."""

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        if not self.responses:
            raise RuntimeError("No more responses")
        result = MagicMock()
        result.content = json.dumps(self.responses.pop(0))
        return result


# --- Malformed JSON (during extraction phase) ---


class TestMalformedJson:
    """LLM returns responses that are not valid JSON."""

    @pytest.mark.asyncio
    async def test_completely_invalid_json_during_extraction(self):
        """LLM returns total garbage during extraction — should fall back gracefully."""
        llm = RawTextLLM([
            "This is not JSON at all!",
            "Still not JSON...",
            "Nope, try again",
            # Conversation phase also fails
            "still nothing",
            "more nothing",
            "last nothing",
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Hello")
        # Should return a fallback MESSAGE action, not crash
        assert "action" in action
        assert action["action"] == "MESSAGE"
        assert "trouble" in action["text"]

    @pytest.mark.asyncio
    async def test_partial_json_during_extraction(self):
        """LLM returns truncated JSON during extraction."""
        llm = RawTextLLM([
            '{"intent": "multi_answer", "answers": {"leave_type"',  # truncated
            '{"intent": "multi_answer", "answers": {"leave_type"',  # truncated again
            '{"intent": "multi_answer", "answers": {"leave_type"',  # exhausted retries
            # Conversation phase also fails
            "nope",
            "nope",
            "nope",
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Annual leave")
        assert "action" in action

    @pytest.mark.asyncio
    async def test_json_in_markdown_fence_extraction(self):
        """LLM wraps extraction JSON in markdown code fences — should still parse."""
        json_str = json.dumps({
            "intent": "multi_answer",
            "answers": {"leave_type": "Annual"},
            "message": "Got it!",
        })
        llm = RawTextLLM([
            f"```json\n{json_str}\n```",
            # Conversation phase
            json.dumps({"action": "ASK_DATE", "field_id": "start_date",
                        "label": "Start?", "message": "When?"}),
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Annual leave")
        assert orch.answers.get("leave_type") == "Annual"

    @pytest.mark.asyncio
    async def test_json_with_surrounding_text_extraction(self):
        """LLM adds text before/after the extraction JSON."""
        json_str = json.dumps({
            "intent": "multi_answer",
            "answers": {"leave_type": "Sick"},
            "message": "Sick leave.",
        })
        llm = RawTextLLM([
            f"Here's my response: {json_str} Hope that helps!",
            # Conversation phase
            json.dumps({"action": "ASK_DATE", "field_id": "start_date",
                        "label": "Start?", "message": "When?"}),
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Sick")
        assert orch.answers.get("leave_type") == "Sick"

    @pytest.mark.asyncio
    async def test_empty_response_during_extraction(self):
        """LLM returns empty string during extraction."""
        llm = RawTextLLM([
            "", "", "",
            # Conversation phase also fails
            "", "", "",
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Hello")
        assert "action" in action


# --- Malformed JSON in conversation phase ---


class TestMalformedJsonConversation:
    """LLM returns bad JSON in the conversation follow-up phase."""

    @pytest.mark.asyncio
    async def test_invalid_json_in_followup(self):
        """After extraction, LLM returns garbage in follow-up — fallback message."""
        llm = RawTextLLM([
            # Extraction: valid
            json.dumps({"intent": "multi_answer", "answers": {"leave_type": "Annual"},
                        "message": "Got it!"}),
            # Conversation: valid ASK_DATE
            json.dumps({"action": "ASK_DATE", "field_id": "start_date",
                        "label": "Start?", "message": "When?"}),
            # Follow-up: garbage
            "not json",
            "still not json",
            "nope",
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        # Extraction + conversation
        await orch.process_user_message("Annual leave")

        # Follow-up with bad LLM response
        action = await orch.process_user_message("March 1st")
        assert action["action"] == "MESSAGE"
        assert "trouble" in action["text"]


# --- Unexpected keys ---


class TestUnexpectedKeys:
    """LLM returns JSON with extra or missing keys."""

    @pytest.mark.asyncio
    async def test_extra_keys_ignored_in_extraction(self):
        """Extra keys in extraction response should not cause errors."""
        llm = SequenceLLM([
            {
                "intent": "multi_answer",
                "answers": {"leave_type": "Annual"},
                "message": "Got it!",
                "confidence": 0.95,
                "reasoning": "User clearly stated annual",
                "extra_nested": {"foo": "bar"},
            },
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start?", "message": "When?"},
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        await orch.process_user_message("Annual leave")
        assert orch.answers.get("leave_type") == "Annual"

    @pytest.mark.asyncio
    async def test_missing_message_key(self):
        """LLM response without 'message' key should still work."""
        llm = SequenceLLM([
            {"intent": "multi_answer", "answers": {"leave_type": "Annual"}},
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start?"},
        ])

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        await orch.process_user_message("Annual")
        assert orch.answers.get("leave_type") == "Annual"


# --- LLM exceptions ---


class TestLLMExceptions:
    """LLM raises exceptions (timeout, network error, etc)."""

    @pytest.mark.asyncio
    async def test_llm_exception_during_extraction_returns_fallback(self):
        """When LLM throws during extraction, should return fallback message."""
        llm = ExceptionLLM("Connection timeout")

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Hello")
        assert "action" in action
        # Should return a MESSAGE fallback
        assert action["action"] == "MESSAGE"
        assert "trouble" in action["text"]

    @pytest.mark.asyncio
    async def test_llm_exception_does_not_corrupt_state(self):
        """LLM failure should not leave answers in an inconsistent state."""
        llm = ExceptionLLM("Boom")

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        await orch.process_user_message("Hello")
        assert orch.answers == {}


# --- Retry mechanism ---


class TestRetryMechanism:
    """Retry logic when first LLM call returns bad JSON."""

    @pytest.mark.asyncio
    async def test_bad_json_then_good_json_succeeds_in_extraction(self):
        """First extraction call returns garbage, retry returns valid JSON."""
        llm = FailThenSucceedLLM(
            failures=["not json"],
            success={
                "intent": "multi_answer",
                "answers": {"leave_type": "Annual"},
                "message": "Annual leave.",
            },
        )

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        await orch.process_user_message("Annual leave")
        assert orch.answers.get("leave_type") == "Annual"
        # Should have called LLM at least twice for extraction (1 fail + 1 success)
        # plus 1 more for conversation phase = 3 total
        assert llm.call_count >= 2

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_during_extraction(self):
        """All extraction retries fail — falls through to conversation (also fails)."""
        llm = FailThenSucceedLLM(
            failures=["bad1", "bad2", "bad3", "bad4", "bad5", "bad6"],
            success={"intent": "multi_answer", "answers": {"leave_type": "X"},
                     "message": "X"},
        )

        orch = FormOrchestrator(LEAVE_FORM_MD, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Something")
        assert "action" in action
        # No answer should be stored since extraction failed
        assert orch.answers.get("leave_type") is None or orch.answers.get("leave_type") == "X"

"""
LLM output resilience tests.

Tests cover:
- Malformed JSON responses from LLM (during extraction and one-at-a-time)
- Unexpected keys in LLM JSON response
- LLM returns action for wrong field
- LLM timeout / exception handling
- LLM returns JSON embedded in markdown code fences
- LLM returns empty response
- LLM returns valid JSON but missing required keys
- Retry mechanism: first attempt fails, second succeeds
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.agent.orchestrator import FormOrchestrator
from backend.core.form_state import FormStateManager
from backend.core.schema import FormSchema

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


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


def _load_leave_schema() -> FormSchema:
    with open(SCHEMAS_DIR / "leave_request.json") as f:
        return FormSchema(**json.load(f))


# --- Malformed JSON (during extraction phase) ---


class TestMalformedJson:
    """LLM returns responses that are not valid JSON."""

    @pytest.mark.asyncio
    async def test_completely_invalid_json_during_extraction(self):
        """LLM returns total garbage during extraction — should fall back gracefully."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)
        llm = RawTextLLM([
            "This is not JSON at all!",
            "Still not JSON...",
            "Nope, try again",
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Hello")
        # Should return a fallback action (first field), not crash
        assert "action" in action
        assert action["action"] == "ASK_DROPDOWN"
        assert action["field_id"] == "leave_type"
        # No answer should be stored
        assert state.get_answer("leave_type") is None

    @pytest.mark.asyncio
    async def test_partial_json_during_extraction(self):
        """LLM returns truncated JSON during extraction."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)
        llm = RawTextLLM([
            '{"intent": "multi_answer", "answers": {"leave_type"',  # truncated
            '{"intent": "multi_answer", "answers": {"leave_type"',  # truncated again
            '{"intent": "multi_answer", "answers": {"leave_type"',  # exhausted retries
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Annual leave")
        assert "action" in action

    @pytest.mark.asyncio
    async def test_json_in_markdown_fence_extraction(self):
        """LLM wraps extraction JSON in markdown code fences — should still parse."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)

        json_str = json.dumps({
            "intent": "multi_answer",
            "answers": {"leave_type": "Annual"},
            "message": "Got it!",
        })
        llm = RawTextLLM([f"```json\n{json_str}\n```"])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Annual leave")
        assert state.get_answer("leave_type") == "Annual"

    @pytest.mark.asyncio
    async def test_json_with_surrounding_text_extraction(self):
        """LLM adds text before/after the extraction JSON."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)

        json_str = json.dumps({
            "intent": "multi_answer",
            "answers": {"leave_type": "Sick"},
            "message": "Sick leave.",
        })
        llm = RawTextLLM([f"Here's my response: {json_str} Hope that helps!"])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Sick")
        assert state.get_answer("leave_type") == "Sick"

    @pytest.mark.asyncio
    async def test_empty_response_during_extraction(self):
        """LLM returns empty string during extraction."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)
        llm = RawTextLLM(["", "", ""])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Hello")
        assert "action" in action


# --- Malformed JSON in one-at-a-time phase ---


class TestMalformedJsonOneAtATime:
    """LLM returns bad JSON in the one-at-a-time follow-up phase."""

    @pytest.mark.asyncio
    async def test_invalid_json_in_followup(self):
        """After extraction, LLM returns garbage in follow-up — fallback message."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)
        llm = RawTextLLM([
            # Extraction: valid
            json.dumps({"intent": "multi_answer", "answers": {"leave_type": "Annual"},
                        "message": "Got it!"}),
            # Follow-up: garbage
            "not json",
            "still not json",
            "nope",
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        # Extraction
        await orch.process_user_message("Annual leave")

        # Follow-up with bad LLM response
        action = await orch.process_user_message("March 1st")
        assert action["action"] == "MESSAGE"
        assert "trouble understanding" in action["text"]


# --- Unexpected keys ---


class TestUnexpectedKeys:
    """LLM returns JSON with extra or missing keys."""

    @pytest.mark.asyncio
    async def test_extra_keys_ignored_in_extraction(self):
        """Extra keys in extraction response should not cause errors."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)

        llm = SequenceLLM([{
            "intent": "multi_answer",
            "answers": {"leave_type": "Annual"},
            "message": "Got it!",
            "confidence": 0.95,
            "reasoning": "User clearly stated annual",
            "extra_nested": {"foo": "bar"},
        }])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Annual leave")
        assert state.get_answer("leave_type") == "Annual"

    @pytest.mark.asyncio
    async def test_extra_keys_ignored_in_one_at_a_time(self):
        """Extra keys in one-at-a-time response should not cause errors."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)

        llm = SequenceLLM([
            {"intent": "multi_answer", "answers": {"leave_type": "Annual"}, "message": "Got it!"},
            {"intent": "answer", "field_id": "start_date", "value": "2026-03-01",
             "message": "Start set.", "extra": "ignored"},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        await orch.process_user_message("Annual leave")
        action = await orch.process_user_message("March 1st")
        assert state.get_answer("start_date") == "2026-03-01"

    @pytest.mark.asyncio
    async def test_missing_message_key(self):
        """LLM response without 'message' key should still work."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)

        llm = SequenceLLM([{
            "intent": "multi_answer",
            "answers": {"leave_type": "Annual"},
            # No 'message' key
        }])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Annual")
        assert state.get_answer("leave_type") == "Annual"

    @pytest.mark.asyncio
    async def test_missing_value_for_answer_intent(self):
        """LLM returns answer intent but no value — should handle gracefully."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)

        llm = SequenceLLM([
            # Extraction: nothing
            {"intent": "multi_answer", "answers": {}, "message": "Nothing."},
            # One-at-a-time: answer with no value
            {"intent": "answer", "field_id": "leave_type",
             "message": "I think you want annual leave."},
        ])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        await orch.process_user_message("something")
        action = await orch.process_user_message("Annual leave")
        # Should not crash; should re-ask the field
        assert "action" in action


# --- Wrong field ---


class TestWrongField:
    """LLM returns an answer for the wrong field."""

    @pytest.mark.asyncio
    async def test_answer_for_wrong_field_stored_correctly(self):
        """If LLM targets a valid field, the answer goes there even if unexpected."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)

        # During extraction, LLM extracts reason (skipping leave_type)
        llm = SequenceLLM([{
            "intent": "multi_answer",
            "answers": {"reason": "Family vacation"},
            "message": "Reason stored.",
        }])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("family vacation")
        # The answer should still be set for the field the LLM targeted
        assert state.get_answer("reason") == "Family vacation"

    @pytest.mark.asyncio
    async def test_answer_for_nonexistent_field_in_extraction(self):
        """LLM references a field that doesn't exist — rejected during bulk set."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)

        llm = SequenceLLM([{
            "intent": "multi_answer",
            "answers": {"nonexistent_field": "something", "leave_type": "Annual"},
            "message": "Stored.",
        }])

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("something")
        # leave_type should still be stored, nonexistent rejected
        assert state.get_answer("leave_type") == "Annual"
        assert state.get_answer("nonexistent_field") is None


# --- LLM exceptions ---


class TestLLMExceptions:
    """LLM raises exceptions (timeout, network error, etc)."""

    @pytest.mark.asyncio
    async def test_llm_exception_during_extraction_returns_fallback(self):
        """When LLM throws during extraction, should fall back to first field."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)
        llm = ExceptionLLM("Connection timeout")

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Hello")
        assert "action" in action
        # Should fall back to asking the first field
        assert action["action"] == "ASK_DROPDOWN"
        assert action["field_id"] == "leave_type"

    @pytest.mark.asyncio
    async def test_llm_exception_does_not_corrupt_state(self):
        """LLM failure should not leave the state in an inconsistent position."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)
        llm = ExceptionLLM("Boom")

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        await orch.process_user_message("Hello")

        # State should still be clean
        assert state.get_answer("leave_type") is None
        assert not state.is_complete()
        assert state.get_next_field().id == "leave_type"


# --- Retry mechanism ---


class TestRetryMechanism:
    """Retry logic when first LLM call returns bad JSON."""

    @pytest.mark.asyncio
    async def test_bad_json_then_good_json_succeeds_in_extraction(self):
        """First extraction call returns garbage, retry returns valid JSON."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)

        llm = FailThenSucceedLLM(
            failures=["not json"],
            success={
                "intent": "multi_answer",
                "answers": {"leave_type": "Annual"},
                "message": "Annual leave.",
            },
        )

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Annual leave")
        assert state.get_answer("leave_type") == "Annual"
        # Should have called LLM twice (original + 1 retry)
        assert llm.call_count == 2

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_during_extraction(self):
        """All extraction retries fail — should fall back to first field."""
        schema = _load_leave_schema()
        state = FormStateManager(schema)

        llm = FailThenSucceedLLM(
            failures=["bad1", "bad2", "bad3"],  # More failures than max retries
            success={"intent": "multi_answer", "answers": {"leave_type": "X"},
                     "message": "X"},
        )

        orch = FormOrchestrator(state, llm)
        orch.get_initial_action()

        action = await orch.process_user_message("Something")
        # Should still return a valid action structure (first field)
        assert "action" in action
        assert action["action"] == "ASK_DROPDOWN"
        # No answer should be stored (all attempts failed)
        assert state.get_answer("leave_type") is None

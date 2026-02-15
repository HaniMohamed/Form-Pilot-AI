"""
Unit tests for the AI Action Protocol.

Tests cover:
- build_message_action
- build_completion_payload
- build_tool_call_action
"""

from backend.core.actions import (
    build_completion_payload,
    build_message_action,
    build_tool_call_action,
)


# =============================================================
# Test: build_completion_payload
# =============================================================


class TestBuildCompletionPayload:
    """Tests for the FORM_COMPLETE payload builder."""

    def test_basic_payload(self):
        answers = {"name": "Alice", "age": "30"}
        payload = build_completion_payload(answers)
        assert payload["action"] == "FORM_COMPLETE"
        assert payload["data"] == {"name": "Alice", "age": "30"}

    def test_payload_with_location(self):
        answers = {
            "incident_type": "Fire",
            "location": {"lat": 24.7136, "lng": 46.6753},
        }
        payload = build_completion_payload(answers)
        assert payload["data"]["location"] == {"lat": 24.7136, "lng": 46.6753}

    def test_empty_answers(self):
        payload = build_completion_payload({})
        assert payload["action"] == "FORM_COMPLETE"
        assert payload["data"] == {}

    def test_payload_is_independent_copy(self):
        """Modifying the returned payload should not affect the original answers."""
        answers = {"name": "Alice"}
        payload = build_completion_payload(answers)
        payload["data"]["name"] = "Bob"
        assert answers["name"] == "Alice"


# =============================================================
# Test: build_message_action
# =============================================================


class TestBuildMessageAction:
    """Tests for the MESSAGE action builder."""

    def test_message_action(self):
        action = build_message_action("I didn't understand that. Could you try again?")
        assert action["action"] == "MESSAGE"
        assert action["text"] == "I didn't understand that. Could you try again?"

    def test_empty_message(self):
        action = build_message_action("")
        assert action["action"] == "MESSAGE"
        assert action["text"] == ""


# =============================================================
# Test: build_tool_call_action
# =============================================================


class TestBuildToolCallAction:
    """Tests for the TOOL_CALL action builder."""

    def test_tool_call_with_args(self):
        action = build_tool_call_action(
            "get_establishments", {"user_id": "123"}, "Fetching establishments..."
        )
        assert action["action"] == "TOOL_CALL"
        assert action["tool_name"] == "get_establishments"
        assert action["tool_args"] == {"user_id": "123"}
        assert action["message"] == "Fetching establishments..."

    def test_tool_call_without_args(self):
        action = build_tool_call_action("get_injury_types")
        assert action["action"] == "TOOL_CALL"
        assert action["tool_name"] == "get_injury_types"
        assert action["tool_args"] == {}
        assert action["message"] == ""

    def test_tool_call_with_message_only(self):
        action = build_tool_call_action("validate_step", message="Validating step 1...")
        assert action["action"] == "TOOL_CALL"
        assert action["tool_name"] == "validate_step"
        assert action["message"] == "Validating step 1..."

"""
Unit tests for the AI Action Protocol.

Tests cover:
- Action builder produces correct JSON for each field type
- Options included for dropdown/checkbox, absent for others
- Label populated from field prompt
- FORM_COMPLETE payload includes all visible answered fields
- FORM_COMPLETE excludes hidden field answers
- MESSAGE action builder
- Pydantic action model serialization
- Integration with FormStateManager for realistic scenarios
"""

import json
from pathlib import Path

import pytest

from backend.core.actions import (
    ActionType,
    AskCheckboxAction,
    AskDateAction,
    AskDatetimeAction,
    AskDropdownAction,
    AskLocationAction,
    AskTextAction,
    FormCompleteAction,
    MessageAction,
    build_action_for_field,
    build_completion_payload,
    build_message_action,
)
from backend.core.form_state import FormStateManager
from backend.core.schema import FormField, FormSchema

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# --- Helpers ---


def make_field(field_id: str, field_type: str, prompt: str, options: list[str] | None = None) -> FormField:
    """Build a FormField for testing."""
    kwargs = {"id": field_id, "type": field_type, "required": True, "prompt": prompt}
    if options is not None:
        kwargs["options"] = options
    return FormField(**kwargs)


# =============================================================
# Test: build_action_for_field — each field type
# =============================================================


class TestBuildActionForField:
    """Tests that build_action_for_field produces correct JSON for each type."""

    def test_dropdown_action(self):
        field = make_field("color", "dropdown", "Pick a color", ["Red", "Blue"])
        action = build_action_for_field(field)
        assert action["action"] == "ASK_DROPDOWN"
        assert action["field_id"] == "color"
        assert action["label"] == "Pick a color"
        assert action["options"] == ["Red", "Blue"]

    def test_checkbox_action(self):
        field = make_field("toppings", "checkbox", "Select toppings", ["Cheese", "Peppers"])
        action = build_action_for_field(field)
        assert action["action"] == "ASK_CHECKBOX"
        assert action["field_id"] == "toppings"
        assert action["label"] == "Select toppings"
        assert action["options"] == ["Cheese", "Peppers"]

    def test_text_action(self):
        field = make_field("name", "text", "What is your name?")
        action = build_action_for_field(field)
        assert action["action"] == "ASK_TEXT"
        assert action["field_id"] == "name"
        assert action["label"] == "What is your name?"
        assert "options" not in action

    def test_date_action(self):
        field = make_field("start_date", "date", "Start date?")
        action = build_action_for_field(field)
        assert action["action"] == "ASK_DATE"
        assert action["field_id"] == "start_date"
        assert action["label"] == "Start date?"
        assert "options" not in action

    def test_datetime_action(self):
        field = make_field("event_time", "datetime", "Event time?")
        action = build_action_for_field(field)
        assert action["action"] == "ASK_DATETIME"
        assert action["field_id"] == "event_time"
        assert action["label"] == "Event time?"
        assert "options" not in action

    def test_location_action(self):
        field = make_field("place", "location", "Select location")
        action = build_action_for_field(field)
        assert action["action"] == "ASK_LOCATION"
        assert action["field_id"] == "place"
        assert action["label"] == "Select location"
        assert "options" not in action


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
# Test: Pydantic action models
# =============================================================


class TestActionModels:
    """Tests that Pydantic action models serialize correctly."""

    def test_ask_dropdown_model(self):
        action = AskDropdownAction(field_id="x", label="Pick", options=["A", "B"])
        d = action.model_dump()
        assert d["action"] == "ASK_DROPDOWN"
        assert d["options"] == ["A", "B"]

    def test_ask_checkbox_model(self):
        action = AskCheckboxAction(field_id="x", label="Check", options=["1", "2"])
        d = action.model_dump()
        assert d["action"] == "ASK_CHECKBOX"

    def test_ask_text_model(self):
        action = AskTextAction(field_id="x", label="Type")
        d = action.model_dump()
        assert d["action"] == "ASK_TEXT"
        assert "options" not in d

    def test_ask_date_model(self):
        action = AskDateAction(field_id="x", label="Date")
        d = action.model_dump()
        assert d["action"] == "ASK_DATE"

    def test_ask_datetime_model(self):
        action = AskDatetimeAction(field_id="x", label="Datetime")
        d = action.model_dump()
        assert d["action"] == "ASK_DATETIME"

    def test_ask_location_model(self):
        action = AskLocationAction(field_id="x", label="Location")
        d = action.model_dump()
        assert d["action"] == "ASK_LOCATION"

    def test_form_complete_model(self):
        action = FormCompleteAction(data={"name": "Alice"})
        d = action.model_dump()
        assert d["action"] == "FORM_COMPLETE"
        assert d["data"] == {"name": "Alice"}

    def test_message_model(self):
        action = MessageAction(text="Hello")
        d = action.model_dump()
        assert d["action"] == "MESSAGE"
        assert d["text"] == "Hello"

    def test_json_serialization_round_trip(self):
        action = AskDropdownAction(field_id="color", label="Pick", options=["R", "G"])
        json_str = action.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["action"] == "ASK_DROPDOWN"
        assert parsed["options"] == ["R", "G"]


# =============================================================
# Test: Integration with FormStateManager
# =============================================================


class TestActionIntegration:
    """Tests action building using real schemas and FormStateManager."""

    def test_incident_report_first_action(self):
        with open(SCHEMAS_DIR / "incident_report.json") as f:
            schema = FormSchema(**json.load(f))
        mgr = FormStateManager(schema)

        next_field = mgr.get_next_field()
        action = build_action_for_field(next_field)
        assert action["action"] == "ASK_DROPDOWN"
        assert action["field_id"] == "incident_type"
        assert action["options"] == ["Fire", "Accident", "Injury"]

    def test_incident_report_completion_payload(self):
        with open(SCHEMAS_DIR / "incident_report.json") as f:
            schema = FormSchema(**json.load(f))
        mgr = FormStateManager(schema)

        mgr.set_answer("incident_type", "Accident")
        mgr.set_answer("start_date", "2026-02-11")
        mgr.set_answer("end_date", "2026-02-15")
        mgr.set_answer("followup_reason", "Exceeded threshold")
        mgr.set_answer("location", {"lat": 24.7136, "lng": 46.6753})

        assert mgr.is_complete()
        payload = build_completion_payload(mgr.get_visible_answers())
        assert payload["action"] == "FORM_COMPLETE"
        assert payload["data"]["incident_type"] == "Accident"
        assert payload["data"]["location"] == {"lat": 24.7136, "lng": 46.6753}
        assert len(payload["data"]) == 5

    def test_completion_excludes_hidden_fields(self):
        """When end_date == start_date, followup_reason is hidden."""
        with open(SCHEMAS_DIR / "incident_report.json") as f:
            schema = FormSchema(**json.load(f))
        mgr = FormStateManager(schema)

        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-11")
        mgr.set_answer("end_date", "2026-02-11")  # Same date — followup hidden
        mgr.set_answer("location", {"lat": 24.7136, "lng": 46.6753})

        assert mgr.is_complete()
        payload = build_completion_payload(mgr.get_visible_answers())
        assert "followup_reason" not in payload["data"]
        assert len(payload["data"]) == 4

    def test_leave_request_action_sequence(self):
        with open(SCHEMAS_DIR / "leave_request.json") as f:
            schema = FormSchema(**json.load(f))
        mgr = FormStateManager(schema)

        # First field should be leave_type dropdown
        action = build_action_for_field(mgr.get_next_field())
        assert action["action"] == "ASK_DROPDOWN"
        assert action["field_id"] == "leave_type"
        assert "Annual" in action["options"]

        mgr.set_answer("leave_type", "Sick")

        # Next should be start_date
        action = build_action_for_field(mgr.get_next_field())
        assert action["action"] == "ASK_DATE"
        assert action["field_id"] == "start_date"

"""
Unit tests for the FormStateManager.

Tests cover:
- Loading a valid schema
- get_next_field returns fields in order
- set_answer updates state correctly
- is_complete returns False/True appropriately
- Cascading visibility (answering field A reveals field B)
- Answer validation rejects invalid dropdown, checkbox, text, date, datetime, location
- Answer clearing and re-evaluation
- Conversation history management
- get_visible_answers excludes hidden fields
"""

import json
from pathlib import Path

import pytest

from backend.core.form_state import AnswerValidationError, FormStateManager
from backend.core.schema import FormSchema

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# --- Fixtures ---


@pytest.fixture
def incident_schema() -> FormSchema:
    """Load the incident_report schema."""
    with open(SCHEMAS_DIR / "incident_report.json") as f:
        return FormSchema(**json.load(f))


@pytest.fixture
def leave_schema() -> FormSchema:
    """Load the leave_request schema."""
    with open(SCHEMAS_DIR / "leave_request.json") as f:
        return FormSchema(**json.load(f))


@pytest.fixture
def simple_schema() -> FormSchema:
    """A minimal schema for basic tests."""
    return FormSchema(
        form_id="simple",
        fields=[
            {"id": "name", "type": "text", "required": True, "prompt": "Name?"},
            {"id": "age", "type": "text", "required": True, "prompt": "Age?"},
            {"id": "email", "type": "text", "required": False, "prompt": "Email?"},
        ],
    )


# =============================================================
# Test: Loading and initialization
# =============================================================


class TestInitialization:
    """Tests for creating a FormStateManager."""

    def test_loads_valid_schema(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        assert mgr.schema.form_id == "incident_report"
        assert mgr.answers == {}
        assert mgr.conversation_history == []

    def test_initial_state_not_complete(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        assert mgr.is_complete() is False

    def test_initial_next_field_is_first(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        next_field = mgr.get_next_field()
        assert next_field is not None
        assert next_field.id == "incident_type"


# =============================================================
# Test: get_next_field returns fields in order
# =============================================================


class TestFieldOrder:
    """Tests that fields are returned in schema definition order."""

    def test_fields_in_order(self, simple_schema):
        mgr = FormStateManager(simple_schema)

        # First required field
        assert mgr.get_next_field().id == "name"

        mgr.set_answer("name", "Alice")
        assert mgr.get_next_field().id == "age"

        mgr.set_answer("age", "30")
        # email is optional, so form should be complete
        assert mgr.get_next_field() is None

    def test_incident_field_order(self, incident_schema):
        mgr = FormStateManager(incident_schema)

        # Walk through expected order
        assert mgr.get_next_field().id == "incident_type"
        mgr.set_answer("incident_type", "Fire")

        assert mgr.get_next_field().id == "start_date"
        mgr.set_answer("start_date", "2026-02-10")

        assert mgr.get_next_field().id == "end_date"
        mgr.set_answer("end_date", "2026-02-15")

        # followup_reason should now be visible (end > start)
        assert mgr.get_next_field().id == "followup_reason"
        mgr.set_answer("followup_reason", "Extended duration")

        assert mgr.get_next_field().id == "location"
        mgr.set_answer("location", {"lat": 24.7136, "lng": 46.6753})

        assert mgr.get_next_field() is None
        assert mgr.is_complete() is True


# =============================================================
# Test: set_answer and get_answer
# =============================================================


class TestAnswerManagement:
    """Tests for setting, getting, and clearing answers."""

    def test_set_and_get_answer(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.set_answer("name", "Alice")
        assert mgr.get_answer("name") == "Alice"

    def test_get_answer_unset_returns_none(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        assert mgr.get_answer("name") is None

    def test_clear_answer(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.set_answer("name", "Alice")
        mgr.clear_answer("name")
        assert mgr.get_answer("name") is None
        assert mgr.get_next_field().id == "name"

    def test_clear_nonexistent_answer_no_error(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.clear_answer("name")  # Should not raise

    def test_set_answer_nonexistent_field_raises(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        with pytest.raises(ValueError, match="does not exist"):
            mgr.set_answer("ghost_field", "value")

    def test_get_all_answers(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.set_answer("name", "Alice")
        mgr.set_answer("age", "30")
        answers = mgr.get_all_answers()
        assert answers == {"name": "Alice", "age": "30"}

    def test_overwrite_answer(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.set_answer("name", "Alice")
        mgr.set_answer("name", "Bob")
        assert mgr.get_answer("name") == "Bob"


# =============================================================
# Test: is_complete
# =============================================================


class TestIsComplete:
    """Tests for form completion detection."""

    def test_not_complete_when_missing(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.set_answer("name", "Alice")
        assert mgr.is_complete() is False

    def test_complete_when_all_required_answered(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.set_answer("name", "Alice")
        mgr.set_answer("age", "30")
        # email is optional — form should be complete
        assert mgr.is_complete() is True

    def test_complete_with_optional_answered(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.set_answer("name", "Alice")
        mgr.set_answer("age", "30")
        mgr.set_answer("email", "alice@test.com")
        assert mgr.is_complete() is True

    def test_incident_not_complete_without_conditional_field(self, incident_schema):
        """When followup_reason becomes visible, it must be answered."""
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        mgr.set_answer("end_date", "2026-02-15")
        # followup_reason is now visible and required
        mgr.set_answer("location", {"lat": 24.7136, "lng": 46.6753})
        assert mgr.is_complete() is False  # followup_reason still missing

    def test_incident_complete_with_all_fields(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        mgr.set_answer("end_date", "2026-02-15")
        mgr.set_answer("followup_reason", "Extended duration")
        mgr.set_answer("location", {"lat": 24.7136, "lng": 46.6753})
        assert mgr.is_complete() is True


# =============================================================
# Test: Cascading visibility
# =============================================================


class TestCascadingVisibility:
    """Tests that changing answers re-evaluates visibility and clears hidden fields."""

    def test_conditional_field_appears_when_condition_met(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        mgr.set_answer("end_date", "2026-02-15")

        visible_ids = [f.id for f in mgr.get_visible_fields()]
        assert "followup_reason" in visible_ids

    def test_conditional_field_hidden_when_condition_not_met(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        # end_date same as start — AFTER fails
        mgr.set_answer("end_date", "2026-02-10")

        visible_ids = [f.id for f in mgr.get_visible_fields()]
        assert "followup_reason" not in visible_ids

    def test_clearing_answer_hides_dependent_field(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        mgr.set_answer("end_date", "2026-02-15")
        mgr.set_answer("followup_reason", "Extended duration")

        # Now clear start_date — followup_reason should become hidden
        mgr.clear_answer("start_date")
        visible_ids = [f.id for f in mgr.get_visible_fields()]
        assert "followup_reason" not in visible_ids
        # followup_reason answer should also be cleared
        assert mgr.get_answer("followup_reason") is None

    def test_changing_answer_cascades_visibility(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        mgr.set_answer("end_date", "2026-02-15")
        mgr.set_answer("followup_reason", "Extended")

        # Change end_date so it's no longer after start_date
        mgr.set_answer("end_date", "2026-02-08")

        # followup_reason should be hidden and its answer cleared
        visible_ids = [f.id for f in mgr.get_visible_fields()]
        assert "followup_reason" not in visible_ids
        assert mgr.get_answer("followup_reason") is None

    def test_leave_medical_cert_appears_for_sick(self, leave_schema):
        mgr = FormStateManager(leave_schema)
        mgr.set_answer("leave_type", "Sick")

        visible_ids = [f.id for f in mgr.get_visible_fields()]
        assert "medical_certificate" in visible_ids
        assert "emergency_contact" not in visible_ids

    def test_leave_switching_type_clears_conditional_answer(self, leave_schema):
        mgr = FormStateManager(leave_schema)
        mgr.set_answer("leave_type", "Sick")
        mgr.set_answer("medical_certificate", ["Yes"])

        # Switch to Annual — medical_certificate should be hidden and cleared
        mgr.set_answer("leave_type", "Annual")
        assert mgr.get_answer("medical_certificate") is None
        visible_ids = [f.id for f in mgr.get_visible_fields()]
        assert "medical_certificate" not in visible_ids

    def test_get_visible_answers_excludes_hidden(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        mgr.set_answer("end_date", "2026-02-15")
        mgr.set_answer("followup_reason", "Extended")

        # All four should be in visible answers
        visible = mgr.get_visible_answers()
        assert "followup_reason" in visible

        # Change end_date so followup becomes hidden (cascading clears it)
        mgr.set_answer("end_date", "2026-02-08")
        visible = mgr.get_visible_answers()
        assert "followup_reason" not in visible


# =============================================================
# Test: Answer validation — dropdown
# =============================================================


class TestDropdownValidation:
    """Tests that dropdown answers must be valid options."""

    def test_valid_dropdown_value(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")  # Should not raise
        assert mgr.get_answer("incident_type") == "Fire"

    def test_invalid_dropdown_value(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        with pytest.raises(AnswerValidationError, match="not a valid option"):
            mgr.set_answer("incident_type", "Earthquake")

    def test_dropdown_non_string_value(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        with pytest.raises(AnswerValidationError, match="must be a string"):
            mgr.set_answer("incident_type", 123)


# =============================================================
# Test: Answer validation — checkbox
# =============================================================


class TestCheckboxValidation:
    """Tests that checkbox answers must be a valid list of options."""

    def test_valid_checkbox_value(self, leave_schema):
        mgr = FormStateManager(leave_schema)
        mgr.set_answer("leave_type", "Sick")
        mgr.set_answer("medical_certificate", ["Yes"])
        assert mgr.get_answer("medical_certificate") == ["Yes"]

    def test_checkbox_non_list(self, leave_schema):
        mgr = FormStateManager(leave_schema)
        mgr.set_answer("leave_type", "Sick")
        with pytest.raises(AnswerValidationError, match="must be a list"):
            mgr.set_answer("medical_certificate", "Yes")

    def test_checkbox_empty_list(self, leave_schema):
        mgr = FormStateManager(leave_schema)
        mgr.set_answer("leave_type", "Sick")
        with pytest.raises(AnswerValidationError, match="must not be empty"):
            mgr.set_answer("medical_certificate", [])

    def test_checkbox_invalid_option(self, leave_schema):
        mgr = FormStateManager(leave_schema)
        mgr.set_answer("leave_type", "Sick")
        with pytest.raises(AnswerValidationError, match="Invalid checkbox values"):
            mgr.set_answer("medical_certificate", ["Maybe"])


# =============================================================
# Test: Answer validation — text
# =============================================================


class TestTextValidation:
    """Tests that text answers must be non-empty strings."""

    def test_valid_text(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.set_answer("name", "Alice")
        assert mgr.get_answer("name") == "Alice"

    def test_empty_text(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        with pytest.raises(AnswerValidationError, match="must not be empty"):
            mgr.set_answer("name", "")

    def test_whitespace_only_text(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        with pytest.raises(AnswerValidationError, match="must not be empty"):
            mgr.set_answer("name", "   ")

    def test_text_non_string(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        with pytest.raises(AnswerValidationError, match="must be a string"):
            mgr.set_answer("name", 42)


# =============================================================
# Test: Answer validation — date
# =============================================================


class TestDateValidation:
    """Tests that date answers must be valid ISO date strings."""

    def test_valid_date(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        assert mgr.get_answer("start_date") == "2026-02-10"

    def test_invalid_date(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        with pytest.raises(AnswerValidationError, match="not a valid date"):
            mgr.set_answer("start_date", "not-a-date")

    def test_date_non_string(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        with pytest.raises(AnswerValidationError, match="must be a string"):
            mgr.set_answer("start_date", 20260210)


# =============================================================
# Test: Answer validation — location
# =============================================================


class TestLocationValidation:
    """Tests that location answers must have lat/lng."""

    def test_valid_location(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        mgr.set_answer("end_date", "2026-02-15")
        mgr.set_answer("followup_reason", "Extended")
        mgr.set_answer("location", {"lat": 24.7136, "lng": 46.6753})
        assert mgr.get_answer("location") == {"lat": 24.7136, "lng": 46.6753}

    def test_location_not_dict(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        mgr.set_answer("end_date", "2026-02-15")
        mgr.set_answer("followup_reason", "Extended")
        with pytest.raises(AnswerValidationError, match="must be a dict"):
            mgr.set_answer("location", "24.7, 46.6")

    def test_location_missing_lat(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        mgr.set_answer("end_date", "2026-02-15")
        mgr.set_answer("followup_reason", "Extended")
        with pytest.raises(AnswerValidationError, match="must include 'lat' and 'lng'"):
            mgr.set_answer("location", {"lng": 46.6753})

    def test_location_invalid_lat_range(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        mgr.set_answer("end_date", "2026-02-15")
        mgr.set_answer("followup_reason", "Extended")
        with pytest.raises(AnswerValidationError, match="Latitude.*out of range"):
            mgr.set_answer("location", {"lat": 100.0, "lng": 46.6753})

    def test_location_invalid_lng_range(self, incident_schema):
        mgr = FormStateManager(incident_schema)
        mgr.set_answer("incident_type", "Fire")
        mgr.set_answer("start_date", "2026-02-10")
        mgr.set_answer("end_date", "2026-02-15")
        mgr.set_answer("followup_reason", "Extended")
        with pytest.raises(AnswerValidationError, match="Longitude.*out of range"):
            mgr.set_answer("location", {"lat": 24.7, "lng": 200.0})


# =============================================================
# Test: Conversation history
# =============================================================


class TestConversationHistory:
    """Tests for conversation history management."""

    def test_add_and_get_history(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        mgr.add_message("system", "Welcome")
        mgr.add_message("user", "Hello")
        mgr.add_message("assistant", "What is your name?")

        history = mgr.get_conversation_history()
        assert len(history) == 3
        assert history[0] == {"role": "system", "content": "Welcome"}
        assert history[1] == {"role": "user", "content": "Hello"}
        assert history[2] == {"role": "assistant", "content": "What is your name?"}

    def test_empty_history(self, simple_schema):
        mgr = FormStateManager(simple_schema)
        assert mgr.get_conversation_history() == []

    def test_history_is_copy(self, simple_schema):
        """Modifying returned history should not affect the manager."""
        mgr = FormStateManager(simple_schema)
        mgr.add_message("user", "Hi")
        history = mgr.get_conversation_history()
        history.clear()
        assert len(mgr.get_conversation_history()) == 1


# =============================================================
# Test: Full scenario — leave request
# =============================================================


class TestFullLeaveScenario:
    """End-to-end walkthrough of the leave_request schema."""

    def test_sick_leave_full_flow(self, leave_schema):
        mgr = FormStateManager(leave_schema)

        # Step 1: leave_type
        assert mgr.get_next_field().id == "leave_type"
        mgr.set_answer("leave_type", "Sick")

        # Step 2: start_date
        assert mgr.get_next_field().id == "start_date"
        mgr.set_answer("start_date", "2026-03-01")

        # Step 3: end_date
        assert mgr.get_next_field().id == "end_date"
        mgr.set_answer("end_date", "2026-03-05")

        # Step 4: reason
        assert mgr.get_next_field().id == "reason"
        mgr.set_answer("reason", "Flu")

        # Step 5: medical_certificate (visible because leave_type=Sick)
        assert mgr.get_next_field().id == "medical_certificate"
        mgr.set_answer("medical_certificate", ["Yes"])

        # Form should be complete (handover_notes is optional)
        assert mgr.is_complete() is True

    def test_emergency_leave_full_flow(self, leave_schema):
        mgr = FormStateManager(leave_schema)

        mgr.set_answer("leave_type", "Emergency")
        mgr.set_answer("start_date", "2026-03-01")
        mgr.set_answer("end_date", "2026-03-02")
        mgr.set_answer("reason", "Family emergency")

        # emergency_contact should be visible
        assert mgr.get_next_field().id == "emergency_contact"
        mgr.set_answer("emergency_contact", "John 555-1234")

        assert mgr.is_complete() is True

        # medical_certificate should NOT be in visible fields
        visible_ids = [f.id for f in mgr.get_visible_fields()]
        assert "medical_certificate" not in visible_ids

    def test_annual_leave_no_conditional_fields(self, leave_schema):
        mgr = FormStateManager(leave_schema)

        mgr.set_answer("leave_type", "Annual")
        mgr.set_answer("start_date", "2026-04-01")
        mgr.set_answer("end_date", "2026-04-10")
        mgr.set_answer("reason", "Vacation")

        # Neither medical_certificate nor emergency_contact visible
        visible_ids = [f.id for f in mgr.get_visible_fields()]
        assert "medical_certificate" not in visible_ids
        assert "emergency_contact" not in visible_ids

        assert mgr.is_complete() is True

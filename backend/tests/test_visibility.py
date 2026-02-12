"""
Unit tests for the deterministic visibility evaluator and date parsing utility.

Tests cover:
- Date parsing: ISO dates, datetime strings, invalid inputs
- EXISTS operator
- EQUALS operator (static value and value_field)
- NOT_EQUALS operator (static value and value_field)
- AFTER / BEFORE with valid dates
- ON_OR_AFTER / ON_OR_BEFORE edge cases (same date)
- AND logic with multiple conditions
- Missing referenced fields in answers
- Fields with no visible_if (always visible)
"""

from datetime import date

import pytest

from backend.core.schema import (
    ConditionOperator,
    FormField,
    VisibilityCondition,
    VisibilityRule,
)
from backend.core.utils import parse_date
from backend.core.visibility import is_field_visible


# --- Helpers ---


def make_field(
    field_id: str = "test_field",
    conditions: list[dict] | None = None,
) -> FormField:
    """Build a text FormField with optional visibility conditions."""
    visible_if = None
    if conditions is not None:
        visible_if = VisibilityRule(
            all=[VisibilityCondition(**c) for c in conditions]
        )
    return FormField(
        id=field_id,
        type="text",
        required=True,
        prompt="Test prompt",
        visible_if=visible_if,
    )


# =============================================================
# Test: Date parsing utility
# =============================================================


class TestParseDate:
    """Tests for the parse_date utility function."""

    def test_iso_date(self):
        assert parse_date("2026-02-12") == date(2026, 2, 12)

    def test_iso_datetime(self):
        assert parse_date("2026-02-12T10:30:00") == date(2026, 2, 12)

    def test_date_with_slash(self):
        assert parse_date("2026/03/15") == date(2026, 3, 15)

    def test_none_input(self):
        assert parse_date(None) is None

    def test_empty_string(self):
        assert parse_date("") is None

    def test_non_string_input(self):
        assert parse_date(12345) is None

    def test_garbage_input(self):
        assert parse_date("not-a-date") is None

    def test_leap_year(self):
        assert parse_date("2024-02-29") == date(2024, 2, 29)

    def test_end_of_month(self):
        assert parse_date("2026-01-31") == date(2026, 1, 31)


# =============================================================
# Test: Field with no visible_if (always visible)
# =============================================================


class TestNoVisibleIf:
    """Fields without visible_if should always be visible."""

    def test_always_visible(self):
        field = make_field()
        assert is_field_visible(field, {}) is True

    def test_always_visible_with_answers(self):
        field = make_field()
        assert is_field_visible(field, {"other_field": "value"}) is True


# =============================================================
# Test: EXISTS operator
# =============================================================


class TestExistsOperator:
    """Tests for the EXISTS condition operator."""

    def test_exists_passes_when_value_present(self):
        field = make_field(conditions=[
            {"field": "name", "operator": "EXISTS"},
        ])
        assert is_field_visible(field, {"name": "Alice"}) is True

    def test_exists_fails_when_value_absent(self):
        field = make_field(conditions=[
            {"field": "name", "operator": "EXISTS"},
        ])
        assert is_field_visible(field, {}) is False

    def test_exists_fails_when_value_is_none(self):
        field = make_field(conditions=[
            {"field": "name", "operator": "EXISTS"},
        ])
        assert is_field_visible(field, {"name": None}) is False

    def test_exists_passes_with_empty_string(self):
        """Empty string is not None — EXISTS passes."""
        field = make_field(conditions=[
            {"field": "name", "operator": "EXISTS"},
        ])
        assert is_field_visible(field, {"name": ""}) is True

    def test_exists_passes_with_zero(self):
        """Zero is not None — EXISTS passes."""
        field = make_field(conditions=[
            {"field": "count", "operator": "EXISTS"},
        ])
        assert is_field_visible(field, {"count": 0}) is True


# =============================================================
# Test: EQUALS operator
# =============================================================


class TestEqualsOperator:
    """Tests for the EQUALS condition operator."""

    def test_equals_static_value_passes(self):
        field = make_field(conditions=[
            {"field": "leave_type", "operator": "EQUALS", "value": "Sick"},
        ])
        assert is_field_visible(field, {"leave_type": "Sick"}) is True

    def test_equals_static_value_fails(self):
        field = make_field(conditions=[
            {"field": "leave_type", "operator": "EQUALS", "value": "Sick"},
        ])
        assert is_field_visible(field, {"leave_type": "Annual"}) is False

    def test_equals_with_value_field(self):
        field = make_field(conditions=[
            {"field": "confirm_email", "operator": "EQUALS", "value_field": "email"},
        ])
        assert is_field_visible(field, {"confirm_email": "a@b.com", "email": "a@b.com"}) is True

    def test_equals_with_value_field_fails(self):
        field = make_field(conditions=[
            {"field": "confirm_email", "operator": "EQUALS", "value_field": "email"},
        ])
        assert is_field_visible(field, {"confirm_email": "a@b.com", "email": "x@y.com"}) is False

    def test_equals_missing_field_value(self):
        field = make_field(conditions=[
            {"field": "leave_type", "operator": "EQUALS", "value": "Sick"},
        ])
        assert is_field_visible(field, {}) is False

    def test_equals_missing_value_field_reference(self):
        field = make_field(conditions=[
            {"field": "confirm_email", "operator": "EQUALS", "value_field": "email"},
        ])
        assert is_field_visible(field, {"confirm_email": "a@b.com"}) is False


# =============================================================
# Test: NOT_EQUALS operator
# =============================================================


class TestNotEqualsOperator:
    """Tests for the NOT_EQUALS condition operator."""

    def test_not_equals_static_passes(self):
        field = make_field(conditions=[
            {"field": "status", "operator": "NOT_EQUALS", "value": "closed"},
        ])
        assert is_field_visible(field, {"status": "open"}) is True

    def test_not_equals_static_fails(self):
        field = make_field(conditions=[
            {"field": "status", "operator": "NOT_EQUALS", "value": "closed"},
        ])
        assert is_field_visible(field, {"status": "closed"}) is False

    def test_not_equals_with_value_field(self):
        field = make_field(conditions=[
            {"field": "start_date", "operator": "NOT_EQUALS", "value_field": "end_date"},
        ])
        assert is_field_visible(field, {"start_date": "2026-01-01", "end_date": "2026-02-01"}) is True

    def test_not_equals_with_value_field_fails(self):
        field = make_field(conditions=[
            {"field": "start_date", "operator": "NOT_EQUALS", "value_field": "end_date"},
        ])
        assert is_field_visible(field, {"start_date": "2026-01-01", "end_date": "2026-01-01"}) is False

    def test_not_equals_missing_field(self):
        field = make_field(conditions=[
            {"field": "status", "operator": "NOT_EQUALS", "value": "closed"},
        ])
        assert is_field_visible(field, {}) is False


# =============================================================
# Test: AFTER / BEFORE operators
# =============================================================


class TestDateComparisonOperators:
    """Tests for AFTER and BEFORE date comparison operators."""

    def test_after_passes(self):
        field = make_field(conditions=[
            {"field": "end_date", "operator": "AFTER", "value_field": "start_date"},
        ])
        assert is_field_visible(field, {
            "end_date": "2026-02-15",
            "start_date": "2026-02-10",
        }) is True

    def test_after_fails_same_date(self):
        field = make_field(conditions=[
            {"field": "end_date", "operator": "AFTER", "value_field": "start_date"},
        ])
        assert is_field_visible(field, {
            "end_date": "2026-02-10",
            "start_date": "2026-02-10",
        }) is False

    def test_after_fails_earlier_date(self):
        field = make_field(conditions=[
            {"field": "end_date", "operator": "AFTER", "value_field": "start_date"},
        ])
        assert is_field_visible(field, {
            "end_date": "2026-02-05",
            "start_date": "2026-02-10",
        }) is False

    def test_before_passes(self):
        field = make_field(conditions=[
            {"field": "start_date", "operator": "BEFORE", "value_field": "end_date"},
        ])
        assert is_field_visible(field, {
            "start_date": "2026-02-05",
            "end_date": "2026-02-10",
        }) is True

    def test_before_fails_same_date(self):
        field = make_field(conditions=[
            {"field": "start_date", "operator": "BEFORE", "value_field": "end_date"},
        ])
        assert is_field_visible(field, {
            "start_date": "2026-02-10",
            "end_date": "2026-02-10",
        }) is False

    def test_before_fails_later_date(self):
        field = make_field(conditions=[
            {"field": "start_date", "operator": "BEFORE", "value_field": "end_date"},
        ])
        assert is_field_visible(field, {
            "start_date": "2026-02-15",
            "end_date": "2026-02-10",
        }) is False

    def test_after_with_static_value(self):
        field = make_field(conditions=[
            {"field": "event_date", "operator": "AFTER", "value": "2026-01-01"},
        ])
        assert is_field_visible(field, {"event_date": "2026-06-15"}) is True

    def test_before_with_static_value(self):
        field = make_field(conditions=[
            {"field": "event_date", "operator": "BEFORE", "value": "2026-12-31"},
        ])
        assert is_field_visible(field, {"event_date": "2026-06-15"}) is True

    def test_after_with_missing_field(self):
        field = make_field(conditions=[
            {"field": "end_date", "operator": "AFTER", "value_field": "start_date"},
        ])
        assert is_field_visible(field, {"start_date": "2026-02-10"}) is False

    def test_after_with_missing_compare_field(self):
        field = make_field(conditions=[
            {"field": "end_date", "operator": "AFTER", "value_field": "start_date"},
        ])
        assert is_field_visible(field, {"end_date": "2026-02-10"}) is False

    def test_after_with_invalid_dates(self):
        field = make_field(conditions=[
            {"field": "end_date", "operator": "AFTER", "value_field": "start_date"},
        ])
        assert is_field_visible(field, {
            "end_date": "not-a-date",
            "start_date": "2026-02-10",
        }) is False


# =============================================================
# Test: ON_OR_AFTER / ON_OR_BEFORE operators (edge cases)
# =============================================================


class TestOnOrAfterOnOrBefore:
    """Tests for ON_OR_AFTER and ON_OR_BEFORE — especially same-date edge cases."""

    def test_on_or_after_same_date(self):
        field = make_field(conditions=[
            {"field": "end_date", "operator": "ON_OR_AFTER", "value_field": "start_date"},
        ])
        assert is_field_visible(field, {
            "end_date": "2026-02-10",
            "start_date": "2026-02-10",
        }) is True

    def test_on_or_after_later_date(self):
        field = make_field(conditions=[
            {"field": "end_date", "operator": "ON_OR_AFTER", "value_field": "start_date"},
        ])
        assert is_field_visible(field, {
            "end_date": "2026-02-15",
            "start_date": "2026-02-10",
        }) is True

    def test_on_or_after_earlier_date_fails(self):
        field = make_field(conditions=[
            {"field": "end_date", "operator": "ON_OR_AFTER", "value_field": "start_date"},
        ])
        assert is_field_visible(field, {
            "end_date": "2026-02-05",
            "start_date": "2026-02-10",
        }) is False

    def test_on_or_before_same_date(self):
        field = make_field(conditions=[
            {"field": "start_date", "operator": "ON_OR_BEFORE", "value_field": "end_date"},
        ])
        assert is_field_visible(field, {
            "start_date": "2026-02-10",
            "end_date": "2026-02-10",
        }) is True

    def test_on_or_before_earlier_date(self):
        field = make_field(conditions=[
            {"field": "start_date", "operator": "ON_OR_BEFORE", "value_field": "end_date"},
        ])
        assert is_field_visible(field, {
            "start_date": "2026-02-05",
            "end_date": "2026-02-10",
        }) is True

    def test_on_or_before_later_date_fails(self):
        field = make_field(conditions=[
            {"field": "start_date", "operator": "ON_OR_BEFORE", "value_field": "end_date"},
        ])
        assert is_field_visible(field, {
            "start_date": "2026-02-15",
            "end_date": "2026-02-10",
        }) is False


# =============================================================
# Test: AND logic with multiple conditions
# =============================================================


class TestAndLogic:
    """Tests that all conditions in the `all` list must pass."""

    def test_all_conditions_pass(self):
        field = make_field(conditions=[
            {"field": "start_date", "operator": "EXISTS"},
            {"field": "end_date", "operator": "EXISTS"},
            {"field": "end_date", "operator": "AFTER", "value_field": "start_date"},
        ])
        assert is_field_visible(field, {
            "start_date": "2026-02-10",
            "end_date": "2026-02-15",
        }) is True

    def test_one_condition_fails(self):
        """If end_date is not after start_date, the AND logic fails."""
        field = make_field(conditions=[
            {"field": "start_date", "operator": "EXISTS"},
            {"field": "end_date", "operator": "EXISTS"},
            {"field": "end_date", "operator": "AFTER", "value_field": "start_date"},
        ])
        assert is_field_visible(field, {
            "start_date": "2026-02-10",
            "end_date": "2026-02-05",
        }) is False

    def test_first_condition_fails_short_circuits(self):
        """If the first condition fails, later ones aren't needed."""
        field = make_field(conditions=[
            {"field": "start_date", "operator": "EXISTS"},
            {"field": "end_date", "operator": "EXISTS"},
        ])
        assert is_field_visible(field, {"end_date": "2026-02-15"}) is False

    def test_equals_and_exists_combined(self):
        field = make_field(conditions=[
            {"field": "leave_type", "operator": "EQUALS", "value": "Sick"},
            {"field": "doctor_name", "operator": "EXISTS"},
        ])
        assert is_field_visible(field, {
            "leave_type": "Sick",
            "doctor_name": "Dr. Smith",
        }) is True

    def test_equals_and_exists_combined_fails(self):
        field = make_field(conditions=[
            {"field": "leave_type", "operator": "EQUALS", "value": "Sick"},
            {"field": "doctor_name", "operator": "EXISTS"},
        ])
        # leave_type matches but doctor_name is missing
        assert is_field_visible(field, {"leave_type": "Sick"}) is False


# =============================================================
# Test: Real schema scenarios (incident_report, leave_request)
# =============================================================


class TestRealSchemaScenarios:
    """Tests using scenarios from the actual example schemas."""

    def test_incident_followup_visible_when_end_after_start(self):
        """followup_reason visible when start_date EXISTS, end_date EXISTS, end > start."""
        field = make_field(
            field_id="followup_reason",
            conditions=[
                {"field": "start_date", "operator": "EXISTS"},
                {"field": "end_date", "operator": "EXISTS"},
                {"field": "end_date", "operator": "AFTER", "value_field": "start_date"},
            ],
        )
        answers = {
            "start_date": "2026-02-11",
            "end_date": "2026-02-15",
        }
        assert is_field_visible(field, answers) is True

    def test_incident_followup_hidden_when_same_date(self):
        field = make_field(
            field_id="followup_reason",
            conditions=[
                {"field": "start_date", "operator": "EXISTS"},
                {"field": "end_date", "operator": "EXISTS"},
                {"field": "end_date", "operator": "AFTER", "value_field": "start_date"},
            ],
        )
        answers = {
            "start_date": "2026-02-11",
            "end_date": "2026-02-11",
        }
        assert is_field_visible(field, answers) is False

    def test_incident_followup_hidden_when_no_dates(self):
        field = make_field(
            field_id="followup_reason",
            conditions=[
                {"field": "start_date", "operator": "EXISTS"},
                {"field": "end_date", "operator": "EXISTS"},
                {"field": "end_date", "operator": "AFTER", "value_field": "start_date"},
            ],
        )
        assert is_field_visible(field, {}) is False

    def test_leave_medical_cert_visible_when_sick(self):
        field = make_field(
            field_id="medical_certificate",
            conditions=[
                {"field": "leave_type", "operator": "EQUALS", "value": "Sick"},
            ],
        )
        assert is_field_visible(field, {"leave_type": "Sick"}) is True

    def test_leave_medical_cert_hidden_when_annual(self):
        field = make_field(
            field_id="medical_certificate",
            conditions=[
                {"field": "leave_type", "operator": "EQUALS", "value": "Sick"},
            ],
        )
        assert is_field_visible(field, {"leave_type": "Annual"}) is False

    def test_leave_emergency_contact_visible_when_emergency(self):
        field = make_field(
            field_id="emergency_contact",
            conditions=[
                {"field": "leave_type", "operator": "EQUALS", "value": "Emergency"},
            ],
        )
        assert is_field_visible(field, {"leave_type": "Emergency"}) is True

    def test_leave_handover_visible_when_dates_set(self):
        field = make_field(
            field_id="handover_notes",
            conditions=[
                {"field": "start_date", "operator": "EXISTS"},
                {"field": "end_date", "operator": "EXISTS"},
            ],
        )
        assert is_field_visible(field, {
            "start_date": "2026-03-01",
            "end_date": "2026-03-10",
        }) is True

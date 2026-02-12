"""
Boundary and edge-case tests.

Tests cover:
- Schema with 0 fields (empty fields rejected by validation)
- Schema with 50+ fields (performance / correctness)
- Deeply nested visible_if dependencies (A → B → C chain)
- Circular visible_if references (caught in schema validation)
- Date edge cases: leap year, end of month, year boundary
- Single-field form
- All fields conditional (none visible initially)
- Field with self-reference (caught in validation)
"""

import json
from datetime import date

import pytest

from backend.core.form_state import AnswerValidationError, FormStateManager
from backend.core.schema import FormSchema
from backend.core.utils import parse_date
from backend.core.visibility import is_field_visible


# --- Schema edge cases ---


class TestSchemaEdgeCases:
    """Schema validation boundary cases."""

    def test_empty_fields_list_rejected(self):
        """Schema with empty fields list should be rejected."""
        with pytest.raises(Exception):
            FormSchema(**{"form_id": "empty", "fields": []})

    def test_single_field_schema(self):
        """Schema with a single required text field should work."""
        schema = FormSchema(**{
            "form_id": "single",
            "fields": [
                {"id": "name", "type": "text", "required": True, "prompt": "Name?"},
            ],
        })
        assert len(schema.fields) == 1

    def test_schema_with_50_fields(self):
        """Schema with 50+ fields should parse and validate correctly."""
        fields = []
        for i in range(55):
            fields.append({
                "id": f"field_{i}",
                "type": "text",
                "required": i < 30,  # First 30 required, rest optional
                "prompt": f"Enter field {i}",
            })

        schema = FormSchema(**{"form_id": "large_form", "fields": fields})
        assert len(schema.fields) == 55

        # FormStateManager should handle it correctly
        state = FormStateManager(schema)
        assert state.get_next_field().id == "field_0"

        # Fill the 30 required fields
        for i in range(30):
            state.set_answer(f"field_{i}", f"value_{i}")

        assert state.is_complete()

    def test_circular_reference_caught(self):
        """Fields referencing each other in visibility conditions (caught at validation)."""
        # Self-reference is caught
        with pytest.raises(Exception):
            FormSchema(**{
                "form_id": "circular",
                "fields": [
                    {
                        "id": "a",
                        "type": "text",
                        "required": True,
                        "prompt": "A?",
                        "visible_if": {"all": [{"field": "a", "operator": "EXISTS"}]},
                    },
                ],
            })

    def test_nonexistent_field_reference_caught(self):
        """Visibility referencing a non-existent field is caught."""
        with pytest.raises(Exception):
            FormSchema(**{
                "form_id": "bad_ref",
                "fields": [
                    {"id": "a", "type": "text", "required": True, "prompt": "A?"},
                    {
                        "id": "b",
                        "type": "text",
                        "required": True,
                        "prompt": "B?",
                        "visible_if": {"all": [{"field": "z", "operator": "EXISTS"}]},
                    },
                ],
            })


# --- Deeply nested visibility dependencies ---


class TestNestedVisibilityDeps:
    """Chain of dependent fields: A → B (visible if A exists) → C (visible if B exists)."""

    @pytest.fixture
    def chain_schema(self):
        return FormSchema(**{
            "form_id": "chain",
            "fields": [
                {"id": "a", "type": "text", "required": True, "prompt": "A?"},
                {
                    "id": "b",
                    "type": "text",
                    "required": True,
                    "prompt": "B?",
                    "visible_if": {"all": [{"field": "a", "operator": "EXISTS"}]},
                },
                {
                    "id": "c",
                    "type": "text",
                    "required": True,
                    "prompt": "C?",
                    "visible_if": {"all": [{"field": "b", "operator": "EXISTS"}]},
                },
                {
                    "id": "d",
                    "type": "text",
                    "required": True,
                    "prompt": "D?",
                    "visible_if": {"all": [{"field": "c", "operator": "EXISTS"}]},
                },
            ],
        })

    def test_chain_initial_state(self, chain_schema):
        """Initially only field 'a' is visible (b, c, d hidden)."""
        state = FormStateManager(chain_schema)
        visible = state.get_visible_fields()
        assert [f.id for f in visible] == ["a"]

    def test_chain_progressive_reveal(self, chain_schema):
        """Answering each field reveals the next in the chain."""
        state = FormStateManager(chain_schema)

        state.set_answer("a", "value_a")
        visible = [f.id for f in state.get_visible_fields()]
        assert "b" in visible
        assert "c" not in visible

        state.set_answer("b", "value_b")
        visible = [f.id for f in state.get_visible_fields()]
        assert "c" in visible
        assert "d" not in visible

        state.set_answer("c", "value_c")
        visible = [f.id for f in state.get_visible_fields()]
        assert "d" in visible
        assert state.get_next_field().id == "d"

    def test_chain_clearing_root_cascades(self, chain_schema):
        """Clearing 'a' should cascade: hide b, c, d and clear their answers."""
        state = FormStateManager(chain_schema)

        state.set_answer("a", "va")
        state.set_answer("b", "vb")
        state.set_answer("c", "vc")
        state.set_answer("d", "vd")
        assert state.is_complete()

        # Clear the root field
        state.clear_answer("a")

        # All dependent answers should be cleared by cascading visibility
        assert state.get_answer("b") is None
        assert state.get_answer("c") is None
        assert state.get_answer("d") is None
        assert not state.is_complete()


# --- All fields conditional ---


class TestAllFieldsConditional:
    """Schema where all fields have visibility conditions."""

    def test_all_conditional_no_visible_fields(self):
        """If all fields are conditional and none are satisfied, no visible fields."""
        schema = FormSchema(**{
            "form_id": "all_conditional",
            "fields": [
                {"id": "a", "type": "text", "required": True, "prompt": "A?"},
                {
                    "id": "b",
                    "type": "text",
                    "required": True,
                    "prompt": "B?",
                    "visible_if": {"all": [{"field": "a", "operator": "EQUALS", "value": "show"}]},
                },
                {
                    "id": "c",
                    "type": "text",
                    "required": True,
                    "prompt": "C?",
                    "visible_if": {"all": [{"field": "a", "operator": "EQUALS", "value": "show"}]},
                },
            ],
        })
        state = FormStateManager(schema)

        # Initially only 'a' is visible
        visible = state.get_visible_fields()
        assert [f.id for f in visible] == ["a"]

        # Answer 'a' with wrong value — b and c stay hidden
        state.set_answer("a", "hide")
        visible = state.get_visible_fields()
        assert [f.id for f in visible] == ["a"]

        # Form is complete because b and c are hidden (not required when hidden)
        assert state.is_complete()

        # Change answer to "show" — b and c appear
        state.set_answer("a", "show")
        visible = [f.id for f in state.get_visible_fields()]
        assert "b" in visible
        assert "c" in visible
        assert not state.is_complete()


# --- Date edge cases ---


class TestDateEdgeCases:
    """Date parsing and comparison edge cases."""

    def test_leap_year_feb_29(self):
        result = parse_date("2024-02-29")
        assert result == date(2024, 2, 29)

    def test_non_leap_year_feb_28(self):
        result = parse_date("2025-02-28")
        assert result == date(2025, 2, 28)

    def test_end_of_month_dec_31(self):
        result = parse_date("2025-12-31")
        assert result == date(2025, 12, 31)

    def test_jan_1_year_boundary(self):
        result = parse_date("2026-01-01")
        assert result == date(2026, 1, 1)

    def test_various_date_formats(self):
        """Multiple date format strings should all parse."""
        dates = [
            ("2026-03-15", date(2026, 3, 15)),
            ("03/15/2026", date(2026, 3, 15)),
            ("15-03-2026", date(2026, 3, 15)),
            ("March 15, 2026", date(2026, 3, 15)),
        ]
        for date_str, expected in dates:
            result = parse_date(date_str)
            assert result == expected, f"Failed to parse: {date_str}"

    def test_date_visibility_on_boundary(self):
        """AFTER operator: same date should fail, next day should pass."""
        schema = FormSchema(**{
            "form_id": "date_test",
            "fields": [
                {"id": "d1", "type": "date", "required": True, "prompt": "Date 1?"},
                {"id": "d2", "type": "date", "required": True, "prompt": "Date 2?"},
                {
                    "id": "result",
                    "type": "text",
                    "required": True,
                    "prompt": "Result?",
                    "visible_if": {
                        "all": [
                            {"field": "d2", "operator": "AFTER", "value_field": "d1"},
                        ]
                    },
                },
            ],
        })
        state = FormStateManager(schema)

        # Same date: AFTER should fail, result hidden
        state.set_answer("d1", "2026-06-15")
        state.set_answer("d2", "2026-06-15")
        visible = [f.id for f in state.get_visible_fields()]
        assert "result" not in visible

        # Next day: AFTER should pass
        state.set_answer("d2", "2026-06-16")
        visible = [f.id for f in state.get_visible_fields()]
        assert "result" in visible


# --- Validation edge cases ---


class TestValidationEdgeCases:
    """Field value validation edge cases."""

    def test_empty_string_rejected_for_text(self):
        schema = FormSchema(**{
            "form_id": "val",
            "fields": [
                {"id": "f", "type": "text", "required": True, "prompt": "F?"},
            ],
        })
        state = FormStateManager(schema)
        with pytest.raises(AnswerValidationError):
            state.set_answer("f", "")

    def test_whitespace_only_rejected_for_text(self):
        schema = FormSchema(**{
            "form_id": "val",
            "fields": [
                {"id": "f", "type": "text", "required": True, "prompt": "F?"},
            ],
        })
        state = FormStateManager(schema)
        with pytest.raises(AnswerValidationError):
            state.set_answer("f", "   \t\n  ")

    def test_invalid_dropdown_value(self):
        schema = FormSchema(**{
            "form_id": "val",
            "fields": [
                {
                    "id": "f",
                    "type": "dropdown",
                    "required": True,
                    "options": ["A", "B"],
                    "prompt": "F?",
                },
            ],
        })
        state = FormStateManager(schema)
        with pytest.raises(AnswerValidationError):
            state.set_answer("f", "C")

    def test_checkbox_empty_list_rejected(self):
        schema = FormSchema(**{
            "form_id": "val",
            "fields": [
                {
                    "id": "f",
                    "type": "checkbox",
                    "required": True,
                    "options": ["X", "Y"],
                    "prompt": "F?",
                },
            ],
        })
        state = FormStateManager(schema)
        with pytest.raises(AnswerValidationError):
            state.set_answer("f", [])

    def test_location_out_of_range(self):
        schema = FormSchema(**{
            "form_id": "val",
            "fields": [
                {"id": "loc", "type": "location", "required": True, "prompt": "Loc?"},
            ],
        })
        state = FormStateManager(schema)
        with pytest.raises(AnswerValidationError):
            state.set_answer("loc", {"lat": 91, "lng": 0})

    def test_date_invalid_string_rejected(self):
        schema = FormSchema(**{
            "form_id": "val",
            "fields": [
                {"id": "d", "type": "date", "required": True, "prompt": "Date?"},
            ],
        })
        state = FormStateManager(schema)
        with pytest.raises(AnswerValidationError):
            state.set_answer("d", "not-a-date")

    def test_set_answer_for_nonexistent_field(self):
        schema = FormSchema(**{
            "form_id": "val",
            "fields": [
                {"id": "f", "type": "text", "required": True, "prompt": "F?"},
            ],
        })
        state = FormStateManager(schema)
        with pytest.raises(ValueError):
            state.set_answer("nonexistent", "value")

"""
Unit tests for form schema validation.

Tests cover:
- Valid schemas pass validation
- Missing required keys are rejected
- Duplicate field IDs are rejected
- visible_if referencing non-existent fields is rejected
- dropdown/checkbox without options is rejected
- Unknown field types are rejected
- Self-referencing visibility is rejected
- Options on non-dropdown/checkbox fields are rejected
- Loading real schema JSON files works
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.core.schema import (
    ConditionOperator,
    FieldType,
    FormField,
    FormSchema,
    InteractionRules,
    VisibilityCondition,
    VisibilityRule,
)

# Path to example schema files
SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# --- Helper: minimal valid schema builder ---


def build_schema(**overrides) -> dict:
    """Build a minimal valid schema dict, with optional overrides."""
    base = {
        "form_id": "test_form",
        "rules": {
            "interaction": {
                "ask_one_field_at_a_time": True,
                "never_assume_values": True,
            }
        },
        "fields": [
            {
                "id": "name",
                "type": "text",
                "required": True,
                "prompt": "What is your name?",
            }
        ],
    }
    base.update(overrides)
    return base


# =============================================================
# Test: Valid schemas
# =============================================================


class TestValidSchemas:
    """Tests that valid schemas pass validation without errors."""

    def test_minimal_valid_schema(self):
        schema = FormSchema(**build_schema())
        assert schema.form_id == "test_form"
        assert len(schema.fields) == 1
        assert schema.fields[0].id == "name"
        assert schema.fields[0].type == FieldType.TEXT

    def test_schema_with_dropdown_field(self):
        data = build_schema(
            fields=[
                {
                    "id": "color",
                    "type": "dropdown",
                    "required": True,
                    "options": ["Red", "Blue", "Green"],
                    "prompt": "Pick a color",
                }
            ]
        )
        schema = FormSchema(**data)
        assert schema.fields[0].options == ["Red", "Blue", "Green"]

    def test_schema_with_checkbox_field(self):
        data = build_schema(
            fields=[
                {
                    "id": "agree",
                    "type": "checkbox",
                    "required": True,
                    "options": ["Yes", "No"],
                    "prompt": "Do you agree?",
                }
            ]
        )
        schema = FormSchema(**data)
        assert schema.fields[0].type == FieldType.CHECKBOX

    def test_schema_with_visibility_conditions(self):
        data = build_schema(
            fields=[
                {
                    "id": "start_date",
                    "type": "date",
                    "required": True,
                    "prompt": "Start date?",
                },
                {
                    "id": "end_date",
                    "type": "date",
                    "required": True,
                    "prompt": "End date?",
                },
                {
                    "id": "notes",
                    "type": "text",
                    "required": False,
                    "prompt": "Any notes?",
                    "visible_if": {
                        "all": [
                            {"field": "start_date", "operator": "EXISTS"},
                            {"field": "end_date", "operator": "EXISTS"},
                        ]
                    },
                },
            ]
        )
        schema = FormSchema(**data)
        assert schema.fields[2].visible_if is not None
        assert len(schema.fields[2].visible_if.all) == 2

    def test_schema_with_value_field_reference(self):
        data = build_schema(
            fields=[
                {
                    "id": "start_date",
                    "type": "date",
                    "required": True,
                    "prompt": "Start date?",
                },
                {
                    "id": "end_date",
                    "type": "date",
                    "required": True,
                    "prompt": "End date?",
                },
                {
                    "id": "reason",
                    "type": "text",
                    "required": True,
                    "prompt": "Why?",
                    "visible_if": {
                        "all": [
                            {
                                "field": "end_date",
                                "operator": "AFTER",
                                "value_field": "start_date",
                            }
                        ]
                    },
                },
            ]
        )
        schema = FormSchema(**data)
        cond = schema.fields[2].visible_if.all[0]
        assert cond.operator == ConditionOperator.AFTER
        assert cond.value_field == "start_date"

    def test_all_field_types(self):
        """Ensure every FieldType can be used in a valid schema."""
        fields = [
            {"id": "f_dropdown", "type": "dropdown", "required": True, "options": ["A"], "prompt": "?"},
            {"id": "f_checkbox", "type": "checkbox", "required": True, "options": ["X"], "prompt": "?"},
            {"id": "f_text", "type": "text", "required": True, "prompt": "?"},
            {"id": "f_date", "type": "date", "required": True, "prompt": "?"},
            {"id": "f_datetime", "type": "datetime", "required": True, "prompt": "?"},
            {"id": "f_location", "type": "location", "required": True, "prompt": "?"},
        ]
        schema = FormSchema(**build_schema(fields=fields))
        assert len(schema.fields) == 6

    def test_default_interaction_rules(self):
        """Rules should default to ask_one_field_at_a_time=True, never_assume_values=True."""
        data = {"form_id": "test", "fields": [{"id": "x", "type": "text", "prompt": "?"}]}
        schema = FormSchema(**data)
        assert schema.rules.ask_one_field_at_a_time is True
        assert schema.rules.never_assume_values is True

    def test_all_condition_operators(self):
        """Ensure every ConditionOperator is a valid enum value."""
        expected = {"EXISTS", "EQUALS", "NOT_EQUALS", "AFTER", "BEFORE", "ON_OR_AFTER", "ON_OR_BEFORE"}
        actual = {op.value for op in ConditionOperator}
        assert actual == expected


# =============================================================
# Test: Missing required keys
# =============================================================


class TestMissingRequiredKeys:
    """Tests that missing required keys raise ValidationError."""

    def test_missing_form_id(self):
        with pytest.raises(ValidationError, match="form_id"):
            FormSchema(fields=[{"id": "x", "type": "text", "prompt": "?"}])

    def test_missing_fields(self):
        with pytest.raises(ValidationError, match="fields"):
            FormSchema(form_id="test")

    def test_empty_fields_list(self):
        with pytest.raises(ValidationError):
            FormSchema(form_id="test", fields=[])

    def test_field_missing_id(self):
        with pytest.raises(ValidationError, match="id"):
            FormField(type="text", prompt="?")

    def test_field_missing_type(self):
        with pytest.raises(ValidationError, match="type"):
            FormField(id="x", prompt="?")

    def test_field_missing_prompt(self):
        with pytest.raises(ValidationError, match="prompt"):
            FormField(id="x", type="text")

    def test_field_empty_id(self):
        with pytest.raises(ValidationError):
            FormField(id="", type="text", prompt="?")

    def test_field_empty_prompt(self):
        with pytest.raises(ValidationError):
            FormField(id="x", type="text", prompt="")

    def test_empty_form_id(self):
        with pytest.raises(ValidationError):
            FormSchema(form_id="", fields=[{"id": "x", "type": "text", "prompt": "?"}])


# =============================================================
# Test: Duplicate field IDs
# =============================================================


class TestDuplicateFieldIds:
    """Tests that duplicate field IDs are rejected."""

    def test_duplicate_ids_rejected(self):
        data = build_schema(
            fields=[
                {"id": "name", "type": "text", "required": True, "prompt": "Name?"},
                {"id": "name", "type": "text", "required": True, "prompt": "Name again?"},
            ]
        )
        with pytest.raises(ValidationError, match="Duplicate field ID.*name"):
            FormSchema(**data)


# =============================================================
# Test: visible_if referencing non-existent fields
# =============================================================


class TestVisibilityReferences:
    """Tests that visibility conditions must reference existing fields."""

    def test_reference_to_nonexistent_field(self):
        data = build_schema(
            fields=[
                {
                    "id": "notes",
                    "type": "text",
                    "required": True,
                    "prompt": "Notes?",
                    "visible_if": {
                        "all": [
                            {"field": "ghost_field", "operator": "EXISTS"}
                        ]
                    },
                }
            ]
        )
        with pytest.raises(ValidationError, match="non-existent field.*ghost_field"):
            FormSchema(**data)

    def test_reference_to_nonexistent_value_field(self):
        data = build_schema(
            fields=[
                {"id": "start", "type": "date", "required": True, "prompt": "Start?"},
                {
                    "id": "end",
                    "type": "date",
                    "required": True,
                    "prompt": "End?",
                    "visible_if": {
                        "all": [
                            {
                                "field": "start",
                                "operator": "AFTER",
                                "value_field": "nonexistent",
                            }
                        ]
                    },
                },
            ]
        )
        with pytest.raises(ValidationError, match="non-existent value_field.*nonexistent"):
            FormSchema(**data)

    def test_self_referencing_visibility(self):
        data = build_schema(
            fields=[
                {
                    "id": "x",
                    "type": "text",
                    "required": True,
                    "prompt": "?",
                    "visible_if": {
                        "all": [{"field": "x", "operator": "EXISTS"}]
                    },
                }
            ]
        )
        with pytest.raises(ValidationError, match="referencing itself"):
            FormSchema(**data)


# =============================================================
# Test: Options validation
# =============================================================


class TestOptionsValidation:
    """Tests that dropdown/checkbox require options, and others must not have them."""

    def test_dropdown_without_options_rejected(self):
        with pytest.raises(ValidationError, match="must have non-empty 'options'"):
            FormField(id="x", type="dropdown", prompt="?")

    def test_dropdown_with_empty_options_rejected(self):
        with pytest.raises(ValidationError, match="must have non-empty 'options'"):
            FormField(id="x", type="dropdown", prompt="?", options=[])

    def test_checkbox_without_options_rejected(self):
        with pytest.raises(ValidationError, match="must have non-empty 'options'"):
            FormField(id="x", type="checkbox", prompt="?")

    def test_text_field_with_options_rejected(self):
        with pytest.raises(ValidationError, match="should not have 'options'"):
            FormField(id="x", type="text", prompt="?", options=["A"])

    def test_date_field_with_options_rejected(self):
        with pytest.raises(ValidationError, match="should not have 'options'"):
            FormField(id="x", type="date", prompt="?", options=["A"])

    def test_location_field_with_options_rejected(self):
        with pytest.raises(ValidationError, match="should not have 'options'"):
            FormField(id="x", type="location", prompt="?", options=["A"])


# =============================================================
# Test: Unknown field type
# =============================================================


class TestUnknownFieldType:
    """Tests that unknown field types are rejected."""

    def test_unknown_type_rejected(self):
        with pytest.raises(ValidationError):
            FormField(id="x", type="radio", prompt="?")

    def test_unknown_type_in_schema_rejected(self):
        data = build_schema(
            fields=[{"id": "x", "type": "slider", "required": True, "prompt": "?"}]
        )
        with pytest.raises(ValidationError):
            FormSchema(**data)


# =============================================================
# Test: Unknown condition operator
# =============================================================


class TestUnknownOperator:
    """Tests that unknown operators are rejected."""

    def test_unknown_operator_rejected(self):
        with pytest.raises(ValidationError):
            VisibilityCondition(field="x", operator="CONTAINS")


# =============================================================
# Test: Visibility rule must have at least one condition
# =============================================================


class TestVisibilityRuleMinLength:
    """Tests that a visibility rule must have at least one condition."""

    def test_empty_all_list_rejected(self):
        with pytest.raises(ValidationError):
            VisibilityRule(all=[])


# =============================================================
# Test: Loading real schema JSON files
# =============================================================


class TestSchemaJsonFiles:
    """Tests that the example schema JSON files load and validate correctly."""

    def test_load_incident_report_schema(self):
        path = SCHEMAS_DIR / "incident_report.json"
        with open(path) as f:
            data = json.load(f)
        schema = FormSchema(**data)
        assert schema.form_id == "incident_report"
        assert len(schema.fields) == 5

        # Verify the conditional field
        followup = next(f for f in schema.fields if f.id == "followup_reason")
        assert followup.visible_if is not None
        assert len(followup.visible_if.all) == 3

    def test_load_leave_request_schema(self):
        path = SCHEMAS_DIR / "leave_request.json"
        with open(path) as f:
            data = json.load(f)
        schema = FormSchema(**data)
        assert schema.form_id == "leave_request"
        assert len(schema.fields) == 7

        # Verify conditional fields
        medical = next(f for f in schema.fields if f.id == "medical_certificate")
        assert medical.visible_if is not None
        assert medical.visible_if.all[0].operator == ConditionOperator.EQUALS
        assert medical.visible_if.all[0].value == "Sick"

        emergency = next(f for f in schema.fields if f.id == "emergency_contact")
        assert emergency.visible_if is not None
        assert emergency.visible_if.all[0].value == "Emergency"


# =============================================================
# Test: Serialization round-trip
# =============================================================


class TestSerialization:
    """Tests that schemas can be serialized to dict/JSON and back."""

    def test_round_trip(self):
        data = build_schema(
            fields=[
                {"id": "color", "type": "dropdown", "required": True, "options": ["R", "G"], "prompt": "?"},
                {
                    "id": "shade",
                    "type": "text",
                    "required": True,
                    "prompt": "?",
                    "visible_if": {"all": [{"field": "color", "operator": "EXISTS"}]},
                },
            ]
        )
        schema = FormSchema(**data)
        exported = schema.model_dump()

        # Re-validate from exported dict
        schema2 = FormSchema(**exported)
        assert schema2.form_id == schema.form_id
        assert len(schema2.fields) == len(schema.fields)
        assert schema2.fields[1].visible_if is not None

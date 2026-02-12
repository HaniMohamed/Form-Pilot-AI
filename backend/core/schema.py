"""
Form schema definition and validation models.

These Pydantic models define the contract between the Flutter web app
and the backend. The schema is the single source of truth for all
field definitions, validation rules, and visibility conditions.
"""

from enum import Enum

from pydantic import BaseModel, Field, model_validator


# --- Enums ---


class FieldType(str, Enum):
    """Supported form field types."""

    DROPDOWN = "dropdown"
    CHECKBOX = "checkbox"
    TEXT = "text"
    DATE = "date"
    DATETIME = "datetime"
    LOCATION = "location"


class ConditionOperator(str, Enum):
    """Supported operators for visibility conditions.

    All operators are evaluated deterministically in backend code,
    never by the LLM.
    """

    EXISTS = "EXISTS"
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    AFTER = "AFTER"
    BEFORE = "BEFORE"
    ON_OR_AFTER = "ON_OR_AFTER"
    ON_OR_BEFORE = "ON_OR_BEFORE"


# --- Visibility Condition Models ---


class VisibilityCondition(BaseModel):
    """A single condition within a visibility rule.

    Each condition references another field and applies an operator
    to determine if the owning field should be visible.
    """

    field: str = Field(
        ...,
        description="The field ID to evaluate (must reference an existing field)",
    )
    operator: ConditionOperator = Field(
        ...,
        description="The comparison operator to apply",
    )
    value: str | None = Field(
        default=None,
        description="Static comparison value (for EQUALS, NOT_EQUALS)",
    )
    value_field: str | None = Field(
        default=None,
        description="Dynamic comparison field ID (for AFTER, BEFORE, ON_OR_AFTER, ON_OR_BEFORE)",
    )


class VisibilityRule(BaseModel):
    """Visibility rule wrapping a list of conditions with AND logic.

    All conditions in the `all` list must pass for the field to be visible.
    """

    all: list[VisibilityCondition] = Field(
        ...,
        min_length=1,
        description="List of conditions — all must pass (AND logic)",
    )


# --- Interaction Rules ---


class InteractionRules(BaseModel):
    """Rules that govern how the AI agent interacts with the user."""

    ask_one_field_at_a_time: bool = Field(
        default=True,
        description="AI must ask for exactly one field per turn",
    )
    never_assume_values: bool = Field(
        default=True,
        description="AI must never assume or fabricate field values",
    )


# --- Form Field ---


class FormField(BaseModel):
    """Definition of a single form field.

    Each field has a type, prompt, and optional visibility conditions.
    Dropdown and checkbox fields must include options.
    """

    id: str = Field(
        ...,
        min_length=1,
        description="Unique field identifier",
    )
    type: FieldType = Field(
        ...,
        description="The widget type for this field",
    )
    required: bool = Field(
        default=True,
        description="Whether this field must be answered",
    )
    options: list[str] | None = Field(
        default=None,
        description="Available options (required for dropdown and checkbox types)",
    )
    prompt: str = Field(
        ...,
        min_length=1,
        description="The question to ask the user for this field",
    )
    visible_if: VisibilityRule | None = Field(
        default=None,
        description="Conditional visibility rule (field is always visible if absent)",
    )

    @model_validator(mode="after")
    def validate_options_for_type(self) -> "FormField":
        """Dropdown and checkbox fields must have options defined."""
        types_requiring_options = {FieldType.DROPDOWN, FieldType.CHECKBOX}

        if self.type in types_requiring_options:
            if not self.options or len(self.options) == 0:
                raise ValueError(
                    f"Field '{self.id}' of type '{self.type.value}' must have non-empty 'options'"
                )

        # Fields that don't use options shouldn't have them
        if self.type not in types_requiring_options and self.options is not None:
            raise ValueError(
                f"Field '{self.id}' of type '{self.type.value}' should not have 'options'"
            )

        return self


# --- Top-Level Form Schema ---


class FormSchema(BaseModel):
    """Top-level form schema — the single source of truth.

    Validates structure, field uniqueness, and cross-field references
    in visibility conditions.
    """

    form_id: str = Field(
        ...,
        min_length=1,
        description="Unique form identifier",
    )
    rules: InteractionRules = Field(
        default_factory=InteractionRules,
        description="Interaction rules for the AI agent",
    )
    fields: list[FormField] = Field(
        ...,
        min_length=1,
        description="List of form fields (at least one required)",
    )

    @model_validator(mode="after")
    def validate_cross_field_references(self) -> "FormSchema":
        """Validate field ID uniqueness and visibility condition references."""
        field_ids = set()

        # Check for duplicate field IDs
        for f in self.fields:
            if f.id in field_ids:
                raise ValueError(f"Duplicate field ID: '{f.id}'")
            field_ids.add(f.id)

        # Check that all visibility conditions reference existing fields
        for f in self.fields:
            if f.visible_if is None:
                continue

            for condition in f.visible_if.all:
                # The referenced field must exist in the schema
                if condition.field not in field_ids:
                    raise ValueError(
                        f"Field '{f.id}' has visible_if referencing "
                        f"non-existent field '{condition.field}'"
                    )

                # The referenced value_field (if any) must also exist
                if condition.value_field is not None and condition.value_field not in field_ids:
                    raise ValueError(
                        f"Field '{f.id}' has visible_if referencing "
                        f"non-existent value_field '{condition.value_field}'"
                    )

                # A field should not reference itself in visibility conditions
                if condition.field == f.id:
                    raise ValueError(
                        f"Field '{f.id}' has visible_if referencing itself"
                    )

        return self

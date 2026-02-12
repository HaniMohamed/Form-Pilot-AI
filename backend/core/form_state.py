"""
Form state manager for tracking conversation progress.

Manages the current state of a form-filling session:
- Which fields are visible based on current answers
- Which required fields are still missing
- What the next field to ask is
- Validation of answers per field type
- Cascading visibility when answers change
"""

from datetime import date, datetime
from typing import Any

from dateutil import parser as dateutil_parser

from backend.core.schema import FieldType, FormField, FormSchema
from backend.core.visibility import is_field_visible


class AnswerValidationError(Exception):
    """Raised when an answer fails validation for its field type."""

    def __init__(self, field_id: str, message: str):
        self.field_id = field_id
        self.message = message
        super().__init__(f"Field '{field_id}': {message}")


class FormStateManager:
    """Manages the state of a single form-filling session.

    Tracks answers, evaluates field visibility, determines the next
    field to ask, and validates answers per field type.

    Args:
        schema: A validated FormSchema instance.
    """

    def __init__(self, schema: FormSchema):
        self.schema = schema
        self.answers: dict[str, Any] = {}
        self.conversation_history: list[dict] = []

    # -----------------------------------------------------------------
    # Field resolution
    # -----------------------------------------------------------------

    def get_visible_fields(self) -> list[FormField]:
        """Return all fields that are currently visible based on answers."""
        return [
            field for field in self.schema.fields
            if is_field_visible(field, self.answers)
        ]

    def get_missing_required_fields(self) -> list[FormField]:
        """Return visible, required fields that have not been answered yet."""
        return [
            field for field in self.get_visible_fields()
            if field.required and field.id not in self.answers
        ]

    def get_next_field(self) -> FormField | None:
        """Return the first missing required visible field, or None if complete."""
        missing = self.get_missing_required_fields()
        return missing[0] if missing else None

    def is_complete(self) -> bool:
        """Check if all visible required fields have been answered."""
        return len(self.get_missing_required_fields()) == 0

    # -----------------------------------------------------------------
    # Answer management
    # -----------------------------------------------------------------

    def set_answer(self, field_id: str, value: Any) -> None:
        """Store a validated answer for the given field.

        Validates the answer against the field type, stores it,
        and handles cascading visibility changes.

        Args:
            field_id: The field ID to answer.
            value: The answer value.

        Raises:
            AnswerValidationError: If the value is invalid for the field type.
            ValueError: If the field_id does not exist in the schema.
        """
        field = self._get_field_by_id(field_id)
        if field is None:
            raise ValueError(f"Field '{field_id}' does not exist in the schema")

        # Validate the answer for this field type
        self._validate_answer(field, value)

        # Store the answer
        self.answers[field_id] = value

        # Handle cascading: re-evaluate visibility and clear hidden answered fields
        self._handle_cascading_visibility()

    def get_answer(self, field_id: str) -> Any:
        """Retrieve the current answer for a field, or None if not answered."""
        return self.answers.get(field_id)

    def clear_answer(self, field_id: str) -> None:
        """Remove an answer (for corrections) and handle cascading visibility.

        Args:
            field_id: The field ID to clear.
        """
        if field_id in self.answers:
            del self.answers[field_id]
            self._handle_cascading_visibility()

    def get_all_answers(self) -> dict[str, Any]:
        """Return a copy of all current answers."""
        return dict(self.answers)

    def get_visible_answers(self) -> dict[str, Any]:
        """Return only answers for currently visible fields."""
        visible_ids = {f.id for f in self.get_visible_fields()}
        return {k: v for k, v in self.answers.items() if k in visible_ids}

    def set_answers_bulk(self, answers: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        """Set multiple answers at once, skipping invalid ones.

        Attempts to set each answer individually, collecting successes
        and failures. Handles cascading visibility after all answers are set.

        Args:
            answers: Dict of {field_id: value} pairs to set.

        Returns:
            A tuple of (accepted, rejected) where:
            - accepted: {field_id: value} for successfully stored answers
            - rejected: {field_id: error_message} for answers that failed validation
        """
        accepted: dict[str, Any] = {}
        rejected: dict[str, str] = {}

        for field_id, value in answers.items():
            try:
                field = self._get_field_by_id(field_id)
                if field is None:
                    rejected[field_id] = f"Field '{field_id}' does not exist in the schema"
                    continue

                # Validate the answer
                self._validate_answer(field, value)

                # Store without cascading yet (we'll cascade once at the end)
                self.answers[field_id] = value
                accepted[field_id] = value

            except AnswerValidationError as e:
                rejected[field_id] = e.message
            except Exception as e:
                rejected[field_id] = str(e)

        # Handle cascading visibility once after all answers are set
        if accepted:
            self._handle_cascading_visibility()

        return accepted, rejected

    # -----------------------------------------------------------------
    # Conversation history
    # -----------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history.

        Args:
            role: Message role ("user", "assistant", or "system").
            content: The message text.
        """
        self.conversation_history.append({"role": role, "content": content})

    def get_conversation_history(self) -> list[dict]:
        """Return the full conversation history."""
        return list(self.conversation_history)

    # -----------------------------------------------------------------
    # Answer validation per field type
    # -----------------------------------------------------------------

    def _validate_answer(self, field: FormField, value: Any) -> None:
        """Validate an answer against its field type.

        Args:
            field: The form field definition.
            value: The answer to validate.

        Raises:
            AnswerValidationError: If the value is invalid.
        """
        match field.type:
            case FieldType.DROPDOWN:
                self._validate_dropdown(field, value)
            case FieldType.CHECKBOX:
                self._validate_checkbox(field, value)
            case FieldType.TEXT:
                self._validate_text(field, value)
            case FieldType.DATE:
                self._validate_date(field, value)
            case FieldType.DATETIME:
                self._validate_datetime(field, value)
            case FieldType.LOCATION:
                self._validate_location(field, value)

    def _validate_dropdown(self, field: FormField, value: Any) -> None:
        """Dropdown value must be one of the defined options."""
        if not isinstance(value, str):
            raise AnswerValidationError(field.id, "Dropdown answer must be a string")
        if field.options and value not in field.options:
            raise AnswerValidationError(
                field.id,
                f"'{value}' is not a valid option. Choose from: {field.options}",
            )

    def _validate_checkbox(self, field: FormField, value: Any) -> None:
        """Checkbox value(s) must be a list and a subset of defined options."""
        if not isinstance(value, list):
            raise AnswerValidationError(field.id, "Checkbox answer must be a list")
        if not value:
            raise AnswerValidationError(field.id, "Checkbox answer must not be empty")
        if field.options:
            invalid = [v for v in value if v not in field.options]
            if invalid:
                raise AnswerValidationError(
                    field.id,
                    f"Invalid checkbox values: {invalid}. Choose from: {field.options}",
                )

    def _validate_text(self, field: FormField, value: Any) -> None:
        """Text value must be a non-empty string."""
        if not isinstance(value, str):
            raise AnswerValidationError(field.id, "Text answer must be a string")
        if not value.strip():
            raise AnswerValidationError(field.id, "Text answer must not be empty")

    def _validate_date(self, field: FormField, value: Any) -> None:
        """Date value must be a valid ISO date string (YYYY-MM-DD)."""
        if not isinstance(value, str):
            raise AnswerValidationError(field.id, "Date answer must be a string")
        try:
            parsed = dateutil_parser.parse(value)
            # Ensure it's a valid date
            if not isinstance(parsed.date(), date):
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise AnswerValidationError(
                field.id, f"'{value}' is not a valid date"
            )

    def _validate_datetime(self, field: FormField, value: Any) -> None:
        """Datetime value must be a valid ISO datetime string."""
        if not isinstance(value, str):
            raise AnswerValidationError(field.id, "Datetime answer must be a string")
        try:
            parsed = dateutil_parser.parse(value)
            if not isinstance(parsed, datetime):
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise AnswerValidationError(
                field.id, f"'{value}' is not a valid datetime"
            )

    def _validate_location(self, field: FormField, value: Any) -> None:
        """Location value must be a dict with lat (float) and lng (float)."""
        if not isinstance(value, dict):
            raise AnswerValidationError(field.id, "Location answer must be a dict with 'lat' and 'lng'")
        if "lat" not in value or "lng" not in value:
            raise AnswerValidationError(field.id, "Location must include 'lat' and 'lng'")
        try:
            lat = float(value["lat"])
            lng = float(value["lng"])
        except (ValueError, TypeError):
            raise AnswerValidationError(field.id, "'lat' and 'lng' must be numeric")
        if not (-90 <= lat <= 90):
            raise AnswerValidationError(field.id, f"Latitude {lat} out of range (-90 to 90)")
        if not (-180 <= lng <= 180):
            raise AnswerValidationError(field.id, f"Longitude {lng} out of range (-180 to 180)")

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _get_field_by_id(self, field_id: str) -> FormField | None:
        """Look up a field by its ID."""
        for field in self.schema.fields:
            if field.id == field_id:
                return field
        return None

    def _handle_cascading_visibility(self) -> None:
        """Re-evaluate visibility and clear answers for fields that became hidden.

        When an answer changes, some conditional fields may become hidden.
        If a hidden field was already answered, its answer is removed to
        keep state consistent.
        """
        visible_ids = {f.id for f in self.get_visible_fields()}

        # Find answered fields that are no longer visible
        hidden_answered = [
            field_id for field_id in list(self.answers.keys())
            if field_id not in visible_ids
        ]

        # Clear them (this may trigger further cascading, so we loop)
        for field_id in hidden_answered:
            del self.answers[field_id]

        # If we cleared any, re-check (handles chained dependencies)
        if hidden_answered:
            self._handle_cascading_visibility()

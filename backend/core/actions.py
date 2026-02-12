"""
AI Action Protocol — structured output models.

Defines the action types the AI returns to the Flutter web app.
Each action maps to a specific UI widget or behavior. The web app
reads the action JSON and renders the appropriate component.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from backend.core.schema import FieldType, FormField


# --- Action Type Enum ---


class ActionType(str, Enum):
    """All supported AI action types."""

    ASK_DROPDOWN = "ASK_DROPDOWN"
    ASK_CHECKBOX = "ASK_CHECKBOX"
    ASK_TEXT = "ASK_TEXT"
    ASK_DATE = "ASK_DATE"
    ASK_DATETIME = "ASK_DATETIME"
    ASK_LOCATION = "ASK_LOCATION"
    FORM_COMPLETE = "FORM_COMPLETE"
    MESSAGE = "MESSAGE"


# --- Action Models ---


class AskDropdownAction(BaseModel):
    """Instructs the UI to render a dropdown selector."""

    action: ActionType = ActionType.ASK_DROPDOWN
    field_id: str
    label: str
    options: list[str]


class AskCheckboxAction(BaseModel):
    """Instructs the UI to render a checkbox group."""

    action: ActionType = ActionType.ASK_CHECKBOX
    field_id: str
    label: str
    options: list[str]


class AskTextAction(BaseModel):
    """Instructs the UI to render a text input."""

    action: ActionType = ActionType.ASK_TEXT
    field_id: str
    label: str


class AskDateAction(BaseModel):
    """Instructs the UI to render a date picker."""

    action: ActionType = ActionType.ASK_DATE
    field_id: str
    label: str


class AskDatetimeAction(BaseModel):
    """Instructs the UI to render a date+time picker."""

    action: ActionType = ActionType.ASK_DATETIME
    field_id: str
    label: str


class AskLocationAction(BaseModel):
    """Instructs the UI to render a location picker."""

    action: ActionType = ActionType.ASK_LOCATION
    field_id: str
    label: str


class FormCompleteAction(BaseModel):
    """Signals that all required fields are filled. Contains the final data."""

    action: ActionType = ActionType.FORM_COMPLETE
    data: dict[str, Any]


class MessageAction(BaseModel):
    """A conversational message (clarification, error, greeting, etc)."""

    action: ActionType = ActionType.MESSAGE
    text: str


# --- Union type for all actions ---

AIAction = (
    AskDropdownAction
    | AskCheckboxAction
    | AskTextAction
    | AskDateAction
    | AskDatetimeAction
    | AskLocationAction
    | FormCompleteAction
    | MessageAction
)


# --- Mapping from FieldType to ActionType ---

_FIELD_TYPE_TO_ACTION: dict[FieldType, ActionType] = {
    FieldType.DROPDOWN: ActionType.ASK_DROPDOWN,
    FieldType.CHECKBOX: ActionType.ASK_CHECKBOX,
    FieldType.TEXT: ActionType.ASK_TEXT,
    FieldType.DATE: ActionType.ASK_DATE,
    FieldType.DATETIME: ActionType.ASK_DATETIME,
    FieldType.LOCATION: ActionType.ASK_LOCATION,
}


# --- Action Builders ---


def build_action_for_field(field: FormField) -> dict:
    """Build the correct action dict for a given form field.

    Maps the field type to the appropriate ASK_* action and populates
    the label from the field prompt. Includes options for dropdown/checkbox.

    Args:
        field: The form field to build an action for.

    Returns:
        A dict representing the action JSON.
    """
    action_type = _FIELD_TYPE_TO_ACTION.get(field.type)
    if action_type is None:
        raise ValueError(f"No action mapping for field type: {field.type}")

    base = {
        "action": action_type.value,
        "field_id": field.id,
        "label": field.prompt,
    }

    # Include options for dropdown and checkbox
    if field.type in {FieldType.DROPDOWN, FieldType.CHECKBOX} and field.options:
        base["options"] = field.options

    return base


def build_completion_payload(visible_answers: dict[str, Any]) -> dict:
    """Build the FORM_COMPLETE action payload.

    Takes only the visible answers (hidden field answers should already
    be excluded by the caller) and assembles the final data.

    Args:
        visible_answers: Answers for currently visible fields only.

    Returns:
        A dict representing the FORM_COMPLETE action JSON.
    """
    return {
        "action": ActionType.FORM_COMPLETE.value,
        "data": dict(visible_answers),
    }


def build_message_action(text: str) -> dict:
    """Build a MESSAGE action for conversational responses.

    Args:
        text: The message text to display.

    Returns:
        A dict representing the MESSAGE action JSON.
    """
    return {
        "action": ActionType.MESSAGE.value,
        "text": text,
    }

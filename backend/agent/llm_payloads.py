"""
Pydantic models for validating/normalizing LLM JSON payloads.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class _BasePayload(BaseModel):
    model_config = ConfigDict(extra="allow")


class MultiAnswerPayload(_BasePayload):
    intent: Literal["multi_answer"]
    answers: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None


class MessagePayload(_BasePayload):
    action: Literal["MESSAGE"]
    text: str | None = None
    message: str | None = None

    @model_validator(mode="after")
    def ensure_text(self):
        if not (self.text or self.message):
            raise ValueError("MESSAGE must include 'text' or 'message'.")
        if not self.text and self.message:
            self.text = self.message
        return self


class AskTextPayload(_BasePayload):
    action: Literal["ASK_TEXT"]
    field_id: str
    label: str | None = None
    message: str | None = None


class AskDatePayload(_BasePayload):
    action: Literal["ASK_DATE"]
    field_id: str
    label: str | None = None
    message: str | None = None


class AskDatetimePayload(_BasePayload):
    action: Literal["ASK_DATETIME"]
    field_id: str
    label: str | None = None
    message: str | None = None


class AskLocationPayload(_BasePayload):
    action: Literal["ASK_LOCATION"]
    field_id: str
    label: str | None = None
    message: str | None = None


class AskDropdownPayload(_BasePayload):
    action: Literal["ASK_DROPDOWN"]
    field_id: str
    options: list[Any] = Field(default_factory=list)
    label: str | None = None
    message: str | None = None


class AskCheckboxPayload(_BasePayload):
    action: Literal["ASK_CHECKBOX"]
    field_id: str
    options: list[Any] = Field(default_factory=list)
    label: str | None = None
    message: str | None = None


class ToolCallPayload(_BasePayload):
    action: Literal["TOOL_CALL"]
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None


class FormCompletePayload(_BasePayload):
    action: Literal["FORM_COMPLETE"]
    data: dict[str, Any] | None = None
    message: str | None = None


def validate_llm_payload(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Validate and normalize an LLM payload with pydantic models."""
    intent = payload.get("intent")
    action = payload.get("action")
    model: type[BaseModel] | None = None

    if intent == "multi_answer":
        model = MultiAnswerPayload
    elif action == "MESSAGE":
        model = MessagePayload
    elif action == "ASK_TEXT":
        model = AskTextPayload
    elif action == "ASK_DATE":
        model = AskDatePayload
    elif action == "ASK_DATETIME":
        model = AskDatetimePayload
    elif action == "ASK_LOCATION":
        model = AskLocationPayload
    elif action == "ASK_DROPDOWN":
        model = AskDropdownPayload
    elif action == "ASK_CHECKBOX":
        model = AskCheckboxPayload
    elif action == "TOOL_CALL":
        model = ToolCallPayload
    elif action == "FORM_COMPLETE":
        model = FormCompletePayload
    else:
        return None, "Payload must contain a valid 'action' or intent='multi_answer'."

    try:
        validated = model.model_validate(payload)
    except ValidationError as e:
        return None, str(e)

    return validated.model_dump(exclude_none=True), None

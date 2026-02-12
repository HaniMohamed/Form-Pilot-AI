"""
System prompt and context builder for the form-filling agent.

The prompt instructs the LLM to:
- Act as a conversational form-filling assistant
- Ask one field at a time
- Never assume or fabricate values
- Return structured JSON output
- Handle corrections gracefully
- Detect when the user is answering vs. asking a question vs. correcting
"""

import json
from typing import Any

from backend.core.schema import FormField, FormSchema


SYSTEM_PROMPT_TEMPLATE = """\
You are FormPilot AI, a conversational form-filling assistant. Your job is to \
help the user complete a form by asking one question at a time and collecting \
their answers.

## Rules
1. Ask for exactly ONE field at a time — never skip ahead or batch questions.
2. NEVER assume, guess, or fabricate values. Only use what the user provides.
3. Always respond with valid JSON matching the format described below.
4. Use the field's prompt as your question, but you may rephrase it naturally.
5. For dropdown/checkbox fields, present the available options clearly.
6. If the user's answer is ambiguous, ask for clarification.
7. If the user wants to correct a previous answer, identify which field they \
   want to change.

## Your Response Format
You must ALWAYS respond with a JSON object. Choose ONE of these formats:

### When asking for a field value:
```json
{{"intent": "answer", "field_id": "<field_id>", "value": <extracted_value>, "message": "<friendly message>"}}
```
- `value` should be the extracted answer from the user's message
- For dropdowns: the exact option string from the options list
- For checkboxes: a JSON array of selected option strings
- For dates: ISO format "YYYY-MM-DD"
- For datetimes: ISO format "YYYY-MM-DDTHH:MM:SS"
- For locations: {{"lat": <number>, "lng": <number>}}
- For text: the user's text as-is

### When the user wants to correct a previous answer:
```json
{{"intent": "correction", "field_id": "<field_to_correct>", "message": "<friendly message>"}}
```

### When you need to ask the next question (no answer to extract):
```json
{{"intent": "ask", "message": "<your question to the user>"}}
```

### When you need to clarify or the message is not an answer:
```json
{{"intent": "clarify", "message": "<clarification request>"}}
```

## Current Form Context
{form_context}

## Current Conversation State
{state_context}

## Instructions for This Turn
{turn_instructions}
"""


def build_system_prompt(
    schema: FormSchema,
    answers: dict[str, Any],
    next_field: FormField | None,
    visible_fields: list[FormField],
) -> str:
    """Build the complete system prompt with current form context injected.

    Args:
        schema: The validated form schema.
        answers: Current user answers.
        next_field: The next field to ask (None if form is complete).
        visible_fields: All currently visible fields.

    Returns:
        The fully populated system prompt string.
    """
    form_context = _build_form_context(schema, visible_fields)
    state_context = _build_state_context(answers, next_field)
    turn_instructions = _build_turn_instructions(next_field, answers)

    return SYSTEM_PROMPT_TEMPLATE.format(
        form_context=form_context,
        state_context=state_context,
        turn_instructions=turn_instructions,
    )


def build_user_message(user_text: str) -> str:
    """Wrap the user's raw text for the LLM.

    Args:
        user_text: The raw message from the user.

    Returns:
        The formatted user message.
    """
    return user_text


def _build_form_context(schema: FormSchema, visible_fields: list[FormField]) -> str:
    """Build the form context section showing fields and their status."""
    lines = [f"Form: {schema.form_id}"]
    lines.append(f"Total fields: {len(schema.fields)}")
    lines.append(f"Visible fields: {len(visible_fields)}")
    lines.append("")
    lines.append("Fields:")

    for field in schema.fields:
        is_visible = field in visible_fields
        status = "VISIBLE" if is_visible else "HIDDEN"
        field_info = f"  - {field.id} (type: {field.type.value}, required: {field.required}, status: {status})"
        if field.options:
            field_info += f"\n    options: {field.options}"
        lines.append(field_info)

    return "\n".join(lines)


def _build_state_context(answers: dict[str, Any], next_field: FormField | None) -> str:
    """Build the state context showing current answers and next field."""
    lines = []

    if answers:
        lines.append("Answered fields:")
        for field_id, value in answers.items():
            display_value = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            lines.append(f"  - {field_id}: {display_value}")
    else:
        lines.append("No fields answered yet.")

    lines.append("")

    if next_field:
        lines.append(f"Next required field: {next_field.id}")
        lines.append(f"  type: {next_field.type.value}")
        lines.append(f"  prompt: {next_field.prompt}")
        if next_field.options:
            lines.append(f"  options: {next_field.options}")
    else:
        lines.append("All required fields are complete!")

    return "\n".join(lines)


def _build_turn_instructions(next_field: FormField | None, answers: dict[str, Any]) -> str:
    """Build specific instructions for this conversation turn."""
    if next_field is None:
        return (
            "The form is complete. Summarize the collected data and respond with:\n"
            '{"intent": "ask", "message": "<summary of all answers and confirmation request>"}'
        )

    if not answers:
        # First turn — greet and ask the first question
        return (
            f"This is the start of the conversation. Greet the user briefly and ask "
            f"for the first field: '{next_field.id}'.\n"
            f"Use the field prompt: \"{next_field.prompt}\"\n"
            f"Respond with an 'ask' intent."
        )

    # Subsequent turn — the user just sent a message
    return (
        f"The user has sent a message. Analyze it to determine:\n"
        f"1. Is it an answer to the current field '{next_field.id}'? → Extract the value and respond with 'answer' intent.\n"
        f"2. Is it a request to correct a previous answer? → Respond with 'correction' intent.\n"
        f"3. Is it unclear or a question? → Respond with 'clarify' intent.\n"
        f"\n"
        f"Current field expecting an answer: {next_field.id} (type: {next_field.type.value})"
    )

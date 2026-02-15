"""
System prompt builder for the markdown-driven form-filling agent.

The LLM receives a condensed version of the form context as its system
prompt. For small models (3B–8B), the full markdown is too large and
causes the model to ignore output format instructions. The condenser
extracts only the essential sections (field summary, tool calls,
instructions) to keep the prompt focused.
"""

import json
import re
from typing import Any


# ---------------------------------------------------------------------------
# Form context condenser — keeps prompt short for small models
# ---------------------------------------------------------------------------

# Maximum lines to include from the form markdown.
# Beyond this, the model loses track of JSON output instructions.
_MAX_CONTEXT_LINES = 150

# Sections we want to extract (case-insensitive substring match on headings)
_KEY_SECTIONS = [
    "tool calls",
    "form overview",
    "field summary",
    "conditional logic",
    "chat agent instructions",
]


def condense_form_context(form_context_md: str) -> str:
    """Condense a large form markdown to just the essential sections.

    Extracts key sections like field summaries, tool calls, and
    instructions. Falls back to head+tail truncation if no sections
    are found.

    Args:
        form_context_md: The full markdown form definition.

    Returns:
        A condensed version suitable for LLM system prompts.
    """
    lines = form_context_md.splitlines()

    # If already short enough, return as-is
    if len(lines) <= _MAX_CONTEXT_LINES:
        return form_context_md

    # Try extracting key sections by heading
    extracted = _extract_key_sections(lines)
    if extracted:
        return extracted

    # Fallback: head (overview/tools) + tail (summaries/instructions)
    head = lines[:50]
    tail = lines[-100:]
    return (
        "\n".join(head)
        + "\n\n[... detailed per-field descriptions omitted ...]\n\n"
        + "\n".join(tail)
    )


def _extract_key_sections(lines: list[str]) -> str | None:
    """Extract sections matching _KEY_SECTIONS from markdown lines.

    Returns concatenated sections, or None if fewer than 2 sections found.
    """
    sections: list[str] = []
    capturing = False
    capture_level = 0
    current_buf: list[str] = []

    for line in lines:
        # Detect markdown headings
        heading_match = re.match(r"^(#{1,4})\s+(.*)", line)

        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            # If we're capturing and hit a same/higher-level heading, stop
            if capturing and level <= capture_level:
                sections.append("\n".join(current_buf))
                current_buf = []
                capturing = False

            # Check if this heading matches a key section
            heading_lower = heading_text.lower()
            if any(key in heading_lower for key in _KEY_SECTIONS):
                capturing = True
                capture_level = level
                current_buf = [line]
                continue

        if capturing:
            current_buf.append(line)

    # Don't forget the last section
    if current_buf:
        sections.append("\n".join(current_buf))

    if len(sections) < 2:
        return None

    # Also grab the title (first heading)
    for line in lines:
        if line.startswith("# "):
            return line + "\n\n" + "\n\n".join(sections)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Main conversation prompt — drives field-by-field interaction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """\
You are a JSON-only API called FormPilot AI. You help users fill forms.
You MUST respond with ONLY a valid JSON object. No plain text. No markdown. No explanations.

AVAILABLE JSON RESPONSES (pick exactly one):

1. {{"action": "MESSAGE", "text": "your message here"}}
2. {{"action": "ASK_DROPDOWN", "field_id": "id", "label": "question", "options": ["a","b"], "message": "text"}}
3. {{"action": "ASK_CHECKBOX", "field_id": "id", "label": "question", "options": ["a","b"], "message": "text"}}
4. {{"action": "ASK_TEXT", "field_id": "id", "label": "question", "message": "text"}}
5. {{"action": "ASK_DATE", "field_id": "id", "label": "question", "message": "text"}}
6. {{"action": "ASK_DATETIME", "field_id": "id", "label": "question", "message": "text"}}
7. {{"action": "ASK_LOCATION", "field_id": "id", "label": "question", "message": "text"}}
8. {{"action": "TOOL_CALL", "tool_name": "name", "tool_args": {{}}, "message": "text"}}
9. {{"action": "FORM_COMPLETE", "data": {{"field": "value"}}, "message": "summary"}}

RULES:
- Ask ONE field at a time. Follow the form field order.
- NEVER fabricate or assume values. Only use what the user provides.
- CRITICAL: If a field says "TOOL_CALL FIRST" in the form, you MUST return a TOOL_CALL to fetch the data BEFORE asking the user. NEVER return ASK_DROPDOWN with empty options [].
- When the app returns tool results, use that data to present real options.
- Respond in the same language the user speaks.
- If the user corrects a previous answer, accept the correction.

WRONG (never do this):
{{"action": "ASK_DROPDOWN", "field_id": "selectedEstablishment", "label": "Which?", "options": [], "message": "Choose"}}
This is WRONG because options is empty. You must call get_establishments FIRST.

RIGHT (always do this when options are needed):
Step 1 - fetch data: {{"action": "TOOL_CALL", "tool_name": "get_establishments", "tool_args": {{}}, "message": "Let me look up your establishments."}}
Step 2 - after tool returns data, THEN ask with real options: {{"action": "ASK_DROPDOWN", "field_id": "selectedEstablishment", "label": "Which establishment?", "options": ["Company A", "Company B"], "message": "Which establishment was the injury related to?"}}

EXAMPLE CONVERSATION:
User: "I want to report my injury"
You: {{"action": "TOOL_CALL", "tool_name": "get_establishments", "tool_args": {{}}, "message": "Let me look up your establishments first."}}

User: [Tool result for get_establishments]: {{"establishments": [{{"name": "Company A"}}, {{"name": "Company B"}}]}}
You: {{"action": "ASK_DROPDOWN", "field_id": "selectedEstablishment", "label": "Which establishment?", "options": ["Company A", "Company B"], "message": "Which establishment was the injury related to?"}}

User: "Company A"
You: {{"action": "ASK_DATE", "field_id": "injuryDate", "label": "When did the injury occur?", "message": "When did the injury happen? Please provide the date."}}

=== FORM REFERENCE DATA ===
{form_context_md}
=== END FORM REFERENCE DATA ===

CURRENT STATE:
{state_context}

{next_step_hint}

RESPOND WITH ONLY A JSON OBJECT:"""


# ---------------------------------------------------------------------------
# Extraction prompt — bulk extraction from user's free-text description
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT_TEMPLATE = """\
You are a JSON-only API. You MUST respond with ONLY a valid JSON object.
No plain text. No markdown. No explanations. ONLY JSON.

TASK: The user described data for a form. Extract field values from their message.

RULES:
- ONLY extract values the user explicitly stated. NEVER guess.
- Match values to field IDs from the form below.
- For dates, use ISO format "YYYY-MM-DD".
- Skip fields you are NOT confident about.
- Fields needing tool calls for options — do NOT extract those.

YOUR RESPONSE MUST BE THIS EXACT FORMAT:
{{"intent": "multi_answer", "answers": {{"fieldId": "value"}}, "message": "summary"}}

EXAMPLE:
User says: "I got injured last week at work, it was on January 5th"
Correct response: {{"intent": "multi_answer", "answers": {{"injuryDate": "2026-01-05"}}, "message": "I noted the injury date as January 5th, 2026. Let me help with the remaining fields."}}

User says: "I want to report an injury"
Correct response: {{"intent": "multi_answer", "answers": {{}}, "message": "I understand you want to report an injury. Let me guide you through the form."}}

=== FORM FIELDS REFERENCE ===
{form_context_md}
=== END FORM FIELDS REFERENCE ===

RESPOND WITH ONLY A JSON OBJECT:"""


def build_system_prompt(
    form_context_md: str,
    answers: dict[str, Any],
    conversation_history: list[dict] | None = None,
) -> str:
    """Build the system prompt with condensed form context and current state.

    The form markdown is automatically condensed to keep the prompt
    short enough for small models to follow JSON output instructions.
    """
    condensed = condense_form_context(form_context_md)
    state_context = _build_state_context(answers)
    next_step_hint = _build_next_step_hint(answers, conversation_history)
    return SYSTEM_PROMPT_TEMPLATE.format(
        form_context_md=condensed,
        state_context=state_context,
        next_step_hint=next_step_hint,
    )


def build_extraction_prompt(form_context_md: str) -> str:
    """Build the system prompt for bulk extraction phase.

    Uses condensed form context to avoid overwhelming small models.
    """
    condensed = condense_form_context(form_context_md)
    return EXTRACTION_SYSTEM_PROMPT_TEMPLATE.format(
        form_context_md=condensed,
    )


def _build_state_context(answers: dict[str, Any]) -> str:
    """Build the state context showing current answers."""
    if not answers:
        return "No fields answered yet. This is the start of the form."

    lines = ["Answered fields:"]
    for field_id, value in answers.items():
        display_value = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        lines.append(f"  - {field_id}: {display_value}")

    return "\n".join(lines)


def _build_next_step_hint(
    answers: dict[str, Any],
    conversation_history: list[dict] | None = None,
) -> str:
    """Build a directive hint telling the LLM what to do next.

    This helps small models focus on the immediate next action
    instead of getting lost in the form definition.
    """
    if not answers:
        # Check if the conversation already has tool results
        has_tool_results = False
        if conversation_history:
            for msg in conversation_history:
                if "[Tool result" in msg.get("content", ""):
                    has_tool_results = True
                    break

        if has_tool_results:
            return (
                "YOUR NEXT ACTION: The app has returned tool results. "
                "Use the data to present options to the user as an ASK_DROPDOWN."
            )

        return (
            "YOUR NEXT ACTION: No fields answered yet. "
            "Check the Field Summary Table for field #1. "
            "If it says 'TOOL_CALL FIRST', return a TOOL_CALL to fetch its data. "
            "Do NOT return ASK_DROPDOWN with empty options."
        )

    # Some answers exist — tell the model to find the next unanswered field
    answered_ids = ", ".join(answers.keys())
    return (
        f"YOUR NEXT ACTION: Fields already answered: [{answered_ids}]. "
        "Look at the form definition to find the NEXT required field that "
        "is NOT yet answered. If it needs data from the app, return a TOOL_CALL. "
        "If all required fields are complete, return FORM_COMPLETE with all the data."
    )

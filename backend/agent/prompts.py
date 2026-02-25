"""
System prompt builder for the form-filling agent.

Supports two form definition formats:
1. **Hybrid** (recommended): YAML frontmatter + Markdown body.
   Structured field/tool data is parsed from the YAML header.
   The markdown body provides rich context for the LLM.
2. **Legacy**: Pure markdown with a Field Summary Table.
   Fields are extracted via regex table parsing (backward compat).

The LLM receives a condensed version of the markdown body as its
system prompt. For small models (3B–8B), the full markdown is too
large and causes the model to ignore output format instructions.
"""

import json
import re
from typing import Any

from backend.agent.frontmatter import (
    get_field_type_map,
    get_required_field_ids,
    get_title,
    parse_frontmatter,
)


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


def extract_form_title(form_context_md: str) -> str:
    """Extract the form title from frontmatter or the first markdown heading.

    Checks YAML frontmatter first. Falls back to parsing the first
    '# ' heading in the markdown. Returns 'Form' if nothing is found.

    Args:
        form_context_md: The full form definition (may include frontmatter).

    Returns:
        The form title string.
    """
    # Try frontmatter first
    frontmatter, body = parse_frontmatter(form_context_md)
    fm_title = get_title(frontmatter)
    if fm_title:
        return fm_title

    # Fall back to first markdown heading
    source = body if frontmatter else form_context_md
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            for prefix in ["Form Pilot:", "Form Pilot -", "FormPilot:"]:
                if title.lower().startswith(prefix.lower()):
                    title = title[len(prefix) :].strip()
            return title
    return "Form"


def summarize_required_fields(form_context_md: str) -> str:
    """Build a natural-language summary of the required fields.

    Checks YAML frontmatter first, falls back to parsing the markdown
    Field Summary Table. Groups required fields by type and returns a
    conversational sentence describing what data is needed.

    Args:
        form_context_md: The full form definition (may include frontmatter).

    Returns:
        A human-friendly summary string, or empty string if nothing found.
    """
    fields: list[tuple[str, str]] = []

    # Try frontmatter first
    frontmatter, _ = parse_frontmatter(form_context_md)
    if frontmatter and frontmatter.get("fields"):
        from backend.agent.frontmatter import extract_fields
        for field in extract_fields(frontmatter):
            field_id = field.get("id", "")
            field_type = field.get("type", "").lower()
            req = field.get("required", False)
            if (req is True or (isinstance(req, str) and req.lower() == "true")) and field_id:
                fields.append((field_id, field_type))
    else:
        # Fall back to markdown table parsing
        in_table = False
        for line in form_context_md.splitlines():
            stripped = line.strip()
            if "Field ID" in stripped and "Required" in stripped and "|" in stripped:
                in_table = True
                continue
            if in_table and stripped.startswith("|") and "---" in stripped:
                continue
            if in_table and stripped.startswith("|"):
                cells = [c.strip() for c in stripped.split("|")]
                cells = [c for c in cells if c]
                if len(cells) >= 4:
                    field_id = cells[1].strip("`").strip()
                    field_type = cells[2].strip().lower()
                    required_raw = cells[3].strip().lower()
                    if required_raw.startswith("yes") and field_id:
                        fields.append((field_id, field_type))
            elif in_table and not stripped.startswith("|"):
                break

    if not fields:
        return ""

    return _build_natural_summary(fields)


def _build_natural_summary(fields: list[tuple[str, str]]) -> str:
    """Turn a list of (field_id, type) pairs into a conversational summary.

    Groups related fields by type and produces a warm, natural sentence
    that reads like a person explaining what info they need.
    """
    dates: list[str] = []
    times: list[str] = []
    texts: list[str] = []
    dropdowns: list[str] = []
    locations: list[str] = []

    for field_id, field_type in fields:
        name = _camel_to_words(field_id)
        if field_type in ("date", "datetime"):
            dates.append(name)
        elif field_type == "time":
            times.append(name)
        elif field_type == "text":
            texts.append(name)
        elif field_type in ("dropdown", "checkbox"):
            dropdowns.append(name)
        elif field_type == "location":
            locations.append(name)

    # Build natural phrases for each category
    phrases: list[str] = []

    # Dropdowns first — usually the most recognizable items
    if dropdowns:
        if len(dropdowns) <= 3:
            phrases.append(f"your {_join_names(dropdowns)}")
        else:
            # List a few examples, then summarize the rest naturally
            samples = ", ".join(dropdowns[:3])
            phrases.append(f"your {samples}, and a few other choices")

    # Dates and times — combine into one phrase
    if dates and times:
        phrases.append("relevant dates and times")
    elif dates:
        phrases.append("a few important dates" if len(dates) > 1 else "a date")

    # Text fields
    if texts:
        phrases.append(
            "a description of what happened"
            if len(texts) == 1
            else "some written details"
        )

    # Location
    if locations:
        phrases.append("the location")

    if not phrases:
        return ""

    total = len(fields)
    return (
        f"I'll walk you through about {total} items — "
        f"things like {_join_phrases(phrases)}"
    )


def _camel_to_words(name: str) -> str:
    """Convert a camelCase field ID to a readable lowercase phrase.

    Strips common prefixes/suffixes to produce a clean label.
    Example: 'selectedEstablishment' -> 'establishment'
             'injuryDate' -> 'injury date'
             'locationResults' -> 'location'
    """
    # Remove common prefixes
    for prefix in ["selected", "contributor"]:
        if name.lower().startswith(prefix) and len(name) > len(prefix):
            name = name[len(prefix) :]
            name = name[0].lower() + name[1:]

    # Remove common suffixes that are implementation details
    for suffix in ["Results", "Details", "Data"]:
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]

    # Split on camelCase boundaries
    import re as _re

    return _re.sub(r"([a-z])([A-Z])", r"\1 \2", name).lower()


def _join_names(names: list[str]) -> str:
    """Join names with commas and 'and': ['a', 'b', 'c'] -> 'a, b, and c'."""
    if len(names) == 0:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _join_phrases(phrases: list[str]) -> str:
    """Join phrases naturally with commas and a final 'and'."""
    if len(phrases) <= 2:
        return _join_names(phrases)
    return ", ".join(phrases[:-1]) + f", and {phrases[-1]}"


def extract_required_field_ids(form_context_md: str) -> list[str]:
    """Extract required field IDs from frontmatter or the Field Summary Table.

    Checks YAML frontmatter first for structured field definitions.
    Falls back to parsing the markdown Field Summary Table for backward
    compatibility with forms that don't have frontmatter.

    Args:
        form_context_md: The full form definition (may include frontmatter).

    Returns:
        List of required field_id strings (e.g. ["selectedEstablishment", ...]).
    """
    # Try frontmatter first
    frontmatter, _ = parse_frontmatter(form_context_md)
    if frontmatter and frontmatter.get("fields"):
        return get_required_field_ids(frontmatter)

    # Fall back to markdown table parsing
    return _extract_required_from_table(form_context_md)


def _extract_required_from_table(form_context_md: str) -> list[str]:
    """Legacy: parse required field IDs from a markdown Field Summary Table."""
    required: list[str] = []
    in_table = False

    for line in form_context_md.splitlines():
        stripped = line.strip()
        if "Field ID" in stripped and "Required" in stripped and "|" in stripped:
            in_table = True
            continue
        if in_table and stripped.startswith("|") and "---" in stripped:
            continue
        if in_table and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 4:
                field_id_raw = cells[1]
                required_raw = cells[3]
                field_id = field_id_raw.strip("`").strip()
                if required_raw.strip().lower().startswith("yes"):
                    if field_id and field_id != "Document Uploads":
                        required.append(field_id)
        elif in_table and not stripped.startswith("|"):
            break

    return required


def extract_field_type_map(form_context_md: str) -> dict[str, str]:
    """Extract a mapping of field_id -> field_type from frontmatter or table.

    Checks YAML frontmatter first. Falls back to parsing the markdown
    Field Summary Table for backward compatibility.

    Args:
        form_context_md: The full form definition (may include frontmatter).

    Returns:
        Dict mapping field IDs to their type strings (lowercase).
    """
    # Try frontmatter first
    frontmatter, _ = parse_frontmatter(form_context_md)
    if frontmatter and frontmatter.get("fields"):
        return get_field_type_map(frontmatter)

    # Fall back to markdown table parsing
    return _extract_types_from_table(form_context_md)


def _extract_types_from_table(form_context_md: str) -> dict[str, str]:
    """Legacy: parse field types from a markdown Field Summary Table."""
    field_types: dict[str, str] = {}
    in_table = False

    for line in form_context_md.splitlines():
        stripped = line.strip()
        if "Field ID" in stripped and "Required" in stripped and "|" in stripped:
            in_table = True
            continue
        if in_table and stripped.startswith("|") and "---" in stripped:
            continue
        if in_table and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 4:
                field_id = cells[1].strip("`").strip()
                field_type = cells[2].strip().lower()
                if field_id:
                    field_types[field_id] = field_type
        elif in_table and not stripped.startswith("|"):
            break

    return field_types


def condense_form_context(form_context_md: str) -> str:
    """Condense a large form markdown to just the essential sections.

    If the content has YAML frontmatter, it is stripped — the LLM
    receives only the markdown body. Extracts key sections like field
    summaries, tool calls, and instructions. Falls back to head+tail
    truncation if no sections are found.

    Args:
        form_context_md: The full form definition (may include frontmatter).

    Returns:
        A condensed version suitable for LLM system prompts.
    """
    # Strip frontmatter — the LLM needs only the markdown body
    frontmatter, body = parse_frontmatter(form_context_md)
    source = body if frontmatter else form_context_md
    lines = source.splitlines()

    # If already short enough, return as-is
    if len(lines) <= _MAX_CONTEXT_LINES:
        return source

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
- NEVER re-ask a field that is already in the ALREADY ANSWERED list below. Move to the NEXT unanswered field.
- NEVER fabricate or assume values. Only use what the user provides.
- Keep your tone warm, human, and supportive (not robotic).
- CRITICAL: If a field says "TOOL_CALL FIRST" in the form, you MUST return a TOOL_CALL to fetch the data BEFORE asking the user. NEVER return ASK_DROPDOWN with empty options [].
- CRITICAL: NEVER use MESSAGE to ask the user for field data. Use ASK_TEXT for text/time fields, ASK_DATE for dates, ASK_DROPDOWN for dropdowns, etc. MESSAGE is ONLY for greetings or informational text, NOT for asking questions.
- FORMAT VALIDATION: If the system tells you a user's answer is INVALID (wrong format), you MUST re-ask the same field with a helpful error message explaining what format is expected. Do NOT skip the field or move to the next one.
- CONTEXT VALIDATION: When the system asks you to VALIDATE a text answer, you MUST check if the answer is relevant and appropriate for the question. If the answer is gibberish, random characters, completely unrelated to the question, or nonsensical — re-ask the SAME field using ASK_TEXT with the SAME field_id. Politely explain what kind of answer you need. Only proceed to the next field if the answer genuinely makes sense for the question.
- RE-ASK STYLE: When re-asking after an invalid or irrelevant answer, DO NOT repeat your previous question word-for-word. Acknowledge briefly, explain what is needed, and ask again with different wording.
- When the app returns tool results, use that data to present real options.
- Respond in the same language the user speaks.
- If the user corrects a previous answer, accept the correction.

FRIENDLY STYLE GUIDE (apply for ASK_* messages):
- Keep it short and natural (1-2 sentences).
- Sound supportive, not strict or blaming.
- Prefer simple everyday wording over formal phrasing.
- For invalid input re-asks, use this pattern:
  1) brief acknowledgment (e.g., "Thanks" / "No worries"),
  2) what is missing or wrong,
  3) one clear format/example,
  4) re-ask the same field.
- Vary wording between retries so it feels like a real conversation.

CONTEXT VALIDATION EXAMPLES:
- Question: "Describe how the injury occurred" → Answer: "asdfghjkl" → REJECT (gibberish, re-ask)
- Question: "Describe how the injury occurred" → Answer: "I like pizza" → REJECT (irrelevant, re-ask)
- Question: "Describe how the injury occurred" → Answer: "I fell from a ladder while fixing the roof" → ACCEPT (relevant)
- Question: "What time did the injury occur?" → Answer: "blue sky" → REJECT (not a time, re-ask)
- Question: "What time did the injury occur?" → Answer: "around 10 in the morning" → ACCEPT (valid time)
- Question: "Why was there a delay in reporting?" → Answer: "123456" → REJECT (not a reason, re-ask)
- Question: "Why was there a delay in reporting?" → Answer: "I was hospitalized" → ACCEPT (valid reason)

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

User: "2026-02-01"
You: {{"action": "ASK_TEXT", "field_id": "injuryTime", "label": "What time did the injury occur?", "message": "What time did the injury happen?"}}

User: "10am"
You: {{"action": "ASK_TEXT", "field_id": "injuryOccurred", "label": "Describe the injury", "message": "Please describe what happened."}}

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
    required_fields: list[str] | None = None,
) -> str:
    """Build the system prompt with condensed form context and current state.

    The form markdown is automatically condensed to keep the prompt
    short enough for small models to follow JSON output instructions.
    """
    condensed = condense_form_context(form_context_md)
    state_context = _build_state_context(answers)
    # If required_fields not provided, extract them from the markdown
    if required_fields is None:
        required_fields = extract_required_field_ids(form_context_md)
    next_step_hint = _build_next_step_hint(
        answers, conversation_history, required_fields
    )
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
    required_fields: list[str] | None = None,
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

    # Some answers exist — explicitly list answered fields and forbid re-asking
    answered_list = "\n".join(
        f"  - {fid} = {val}" for fid, val in answers.items()
    )
    answered_ids = ", ".join(answers.keys())

    # Build list of still-missing required fields
    missing_hint = ""
    if required_fields:
        missing = [fid for fid in required_fields if fid not in answers]
        if missing:
            missing_list = ", ".join(missing)
            next_field = missing[0]
            missing_hint = (
                f"\n\nSTILL REQUIRED (you MUST ask these before FORM_COMPLETE):\n"
                f"  [{missing_list}]\n"
                f"  Total remaining: {len(missing)} fields\n"
                f"  NEXT field to ask: {next_field}"
            )
        else:
            missing_hint = (
                "\n\nAll required fields are answered. You may return FORM_COMPLETE."
            )

    return (
        f"ALREADY ANSWERED (do NOT ask these again):\n{answered_list}\n\n"
        f"YOUR NEXT ACTION: Skip all answered fields ({answered_ids}). "
        "Find the NEXT field in the Field Summary Table that is NOT in the "
        "answered list above. If it needs a TOOL_CALL, call the tool. "
        "If it has static options, use ASK_DROPDOWN with those options. "
        "Do NOT return FORM_COMPLETE until ALL required fields are answered."
        f"{missing_hint}"
    )

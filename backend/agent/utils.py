"""
Shared utilities for the FormPilot AI graph nodes.

Contains constants, validation functions, JSON extraction, and the
LLM call-with-retry helper used by both extraction and conversation nodes.
"""

import json
import logging
from datetime import date, datetime
from typing import Any

from dateutil import parser as dateutil_parser
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Valid action types the frontend can handle
VALID_ACTION_TYPES = {
    "MESSAGE",
    "ASK_DROPDOWN",
    "ASK_CHECKBOX",
    "ASK_TEXT",
    "ASK_DATE",
    "ASK_DATETIME",
    "ASK_LOCATION",
    "TOOL_CALL",
    "FORM_COMPLETE",
}

# Maximum retries when LLM returns invalid JSON or invalid actions
MAX_JSON_RETRIES = 3

# Corrective prompt sent when LLM output is not valid JSON.
# Very direct and assertive — small models need blunt instructions.
JSON_RETRY_PROMPT = (
    "WRONG. Your response was NOT valid JSON. "
    "You MUST respond with ONLY a JSON object like: "
    '{"action": "MESSAGE", "text": "hello"} '
    "NO explanations. NO markdown. NO plain text. ONLY JSON. Try again now."
)

# Maximum conversation history messages to include in LLM context
MAX_HISTORY_MESSAGES = 30


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def extract_json(content: str) -> dict | None:
    """Extract a JSON object from LLM output.

    Handles cases where the LLM wraps JSON in markdown code fences.

    Args:
        content: Raw LLM output string.

    Returns:
        Parsed dict, or None if extraction fails.
    """
    # Try direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fence
    if "```" in content:
        parts = content.split("```")
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                continue

    # Try finding { ... } in the content
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(content[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Tool result helpers
# ---------------------------------------------------------------------------


def extract_options_hint(tool_data: dict) -> str:
    """Try to extract human-readable option names from a tool result.

    Looks for common patterns in tool result data (arrays of objects
    with name/value fields) and returns a JSON list of option strings.
    Returns empty string if no options can be extracted.
    """
    options: list[str] = []

    for _key, val in tool_data.items():
        if not isinstance(val, list):
            continue
        for item in val:
            if not isinstance(item, dict):
                continue
            # Try common name patterns
            name = item.get("name")
            if isinstance(name, dict):
                # Bilingual name — prefer English
                eng = name.get("english", "")
                if eng:
                    options.append(eng)
                    continue
            if isinstance(name, str):
                options.append(name)
                continue
            # Try value.english pattern (for LOV data)
            value = item.get("value")
            if isinstance(value, dict):
                eng = value.get("english", "")
                if eng:
                    options.append(eng)
                    continue
            # Try label, title, text
            for field in ("label", "title", "text", "description"):
                v = item.get(field)
                if isinstance(v, str) and v:
                    options.append(v)
                    break

    if options:
        return json.dumps(options)
    return ""


# ---------------------------------------------------------------------------
# Answer validation — validates user answers before storing
# ---------------------------------------------------------------------------


def validate_date_answer(value: str) -> tuple[bool, str]:
    """Validate that a string is a recognizable date.

    Checks for clearly invalid patterns (nonsense strings, impossible
    month/day values) before falling back to dateutil parsing.

    Args:
        value: The user-provided date string.

    Returns:
        A tuple of (is_valid, error_message). error_message is empty if valid.
    """
    stripped = value.strip()
    if not stripped:
        return False, "Date cannot be empty."

    # Reject strings that are purely alphabetic with no digits —
    # these are clearly not dates (e.g. "sdasdsdad")
    if not any(ch.isdigit() for ch in stripped):
        return False, (
            f"'{stripped}' is not a valid date. "
            "Please provide a date like 2026-01-15 or January 15, 2026."
        )

    try:
        parsed = dateutil_parser.parse(stripped, dayfirst=False)
        # Extra sanity: reject dates with impossible month/day that
        # dateutil might silently swap or misparse
        if not isinstance(parsed.date(), date):
            raise ValueError
        return True, ""
    except (ValueError, TypeError, OverflowError):
        return False, (
            f"'{stripped}' is not a valid date. "
            "Please provide a date like 2026-01-15 or January 15, 2026."
        )


def validate_datetime_answer(value: str) -> tuple[bool, str]:
    """Validate that a string is a recognizable datetime.

    Args:
        value: The user-provided datetime string.

    Returns:
        A tuple of (is_valid, error_message).
    """
    stripped = value.strip()
    if not stripped:
        return False, "Datetime cannot be empty."

    if not any(ch.isdigit() for ch in stripped):
        return False, (
            f"'{stripped}' is not a valid date/time. "
            "Please provide something like 2026-01-15 10:30 AM."
        )

    try:
        parsed = dateutil_parser.parse(stripped, dayfirst=False)
        if not isinstance(parsed, datetime):
            raise ValueError
        return True, ""
    except (ValueError, TypeError, OverflowError):
        return False, (
            f"'{stripped}' is not a valid date/time. "
            "Please provide something like 2026-01-15 10:30 AM."
        )


def validate_answer_for_action(
    action_type: str, value: str
) -> tuple[bool, str]:
    """Validate a user's answer based on the ASK_* action type.

    Only validates types that have a clear expected format (dates, times).
    Text fields are accepted as-is since the LLM handles content validation.

    Args:
        action_type: The ASK_* action type (e.g. "ASK_DATE").
        value: The user's raw answer string.

    Returns:
        A tuple of (is_valid, error_message).
    """
    if action_type == "ASK_DATE":
        return validate_date_answer(value)
    elif action_type == "ASK_DATETIME":
        return validate_datetime_answer(value)
    return True, ""


# ---------------------------------------------------------------------------
# LLM call with retry and guard validation
# ---------------------------------------------------------------------------


async def call_llm_with_retry(
    llm: Any,
    messages: list,
    answers: dict[str, Any],
    initial_extraction_done: bool,
    required_fields: list[str],
) -> dict | None:
    """Call the LLM and parse its JSON response, with retries and guards.

    Guards catch common LLM mistakes:
    - Invalid JSON output
    - Unknown action types
    - Re-asking already answered fields
    - MESSAGE instead of ASK_* during active form filling
    - ASK_DROPDOWN/CHECKBOX with empty options
    - Premature FORM_COMPLETE with missing required fields

    Args:
        llm: A LangChain BaseChatModel instance.
        messages: The message list to send (mutated with retry prompts).
        answers: Current answers dict (for guard checks).
        initial_extraction_done: Whether extraction phase is done.
        required_fields: List of required field IDs.

    Returns:
        Parsed JSON dict, or None if all retries fail.
    """
    for attempt in range(MAX_JSON_RETRIES + 1):
        try:
            logger.info(
                "Calling LLM (attempt %d/%d, %d messages)...",
                attempt + 1,
                MAX_JSON_RETRIES + 1,
                len(messages),
            )
            response = await llm.ainvoke(messages)
            content = response.content.strip()

            logger.debug("LLM raw response (first 500 chars): %s", content[:500])

            parsed = extract_json(content)
            if parsed is not None:
                # Validate action type — LLM sometimes invents types
                action = parsed.get("action", "")
                intent = parsed.get("intent", "")
                if action and action not in VALID_ACTION_TYPES and not intent:
                    logger.warning(
                        "LLM returned unknown action type '%s' (attempt %d/%d)",
                        action,
                        attempt + 1,
                        MAX_JSON_RETRIES + 1,
                    )
                    # Convert to MESSAGE if it has text content
                    text = parsed.get("text") or parsed.get("message", "")
                    if text:
                        parsed = {"action": "MESSAGE", "text": text}
                        logger.info("Converted unknown action to MESSAGE")
                        return parsed
                    # Otherwise retry — it's gibberish
                    messages.append(HumanMessage(content=JSON_RETRY_PROMPT))
                    continue

                # Catch ASK_* for a field that's already answered —
                # the model is re-asking instead of moving forward
                asked_field = parsed.get("field_id")
                if (
                    action.startswith("ASK_")
                    and asked_field
                    and asked_field in answers
                ):
                    logger.warning(
                        "LLM re-asked already answered field '%s' — "
                        "retrying for next field",
                        asked_field,
                    )
                    answered = ", ".join(answers.keys())
                    messages.append(HumanMessage(content=(
                        f"WRONG. The field '{asked_field}' is already answered. "
                        f"Already answered fields: [{answered}]. "
                        "Ask the NEXT unanswered field instead."
                    )))
                    continue

                # Catch MESSAGE during active form filling —
                # the model is asking a question without using ASK_* format
                if (
                    action == "MESSAGE"
                    and initial_extraction_done
                    and answers
                    and not parsed.get("field_id")
                ):
                    already_retried_message = any(
                        "use ASK_TEXT" in str(getattr(m, "content", ""))
                        for m in messages
                        if hasattr(m, "content")
                    )
                    if not already_retried_message:
                        logger.warning(
                            "LLM returned MESSAGE during active form filling — "
                            "retrying for proper ASK_* action"
                        )
                        answered = ", ".join(answers.keys())
                        messages.append(HumanMessage(content=(
                            "WRONG format. You returned MESSAGE but you should be "
                            "asking for the next unanswered form field. "
                            f"Already answered: [{answered}]. "
                            "Find the next unanswered field and use the correct "
                            "format: ASK_TEXT, ASK_DATE, ASK_DROPDOWN, etc. "
                            "with a field_id. Do NOT use MESSAGE to ask questions."
                        )))
                        continue

                # Catch ASK_DROPDOWN/ASK_CHECKBOX with empty options —
                # the model skipped the required TOOL_CALL
                if action in ("ASK_DROPDOWN", "ASK_CHECKBOX"):
                    options = parsed.get("options")
                    if not options or (isinstance(options, list) and len(options) == 0):
                        logger.warning(
                            "LLM returned %s with empty options for '%s' — "
                            "retrying to get TOOL_CALL first",
                            action,
                            parsed.get("field_id", "?"),
                        )
                        messages.append(HumanMessage(content=(
                            "WRONG. You returned ASK_DROPDOWN with empty options. "
                            "You do NOT have the options yet. "
                            "You MUST return a TOOL_CALL first to fetch the data. "
                            "Check the form: which tool provides data for this field? "
                            "Return a TOOL_CALL for that tool NOW."
                        )))
                        continue

                # Catch premature FORM_COMPLETE — required fields still missing
                if action == "FORM_COMPLETE" and required_fields:
                    missing = [
                        fid for fid in required_fields
                        if fid not in answers
                    ]
                    if missing:
                        logger.warning(
                            "LLM returned FORM_COMPLETE but %d required "
                            "fields are still missing: %s",
                            len(missing),
                            missing,
                        )
                        missing_list = ", ".join(missing)
                        next_field = missing[0]
                        messages.append(HumanMessage(content=(
                            f"WRONG. You returned FORM_COMPLETE but these "
                            f"required fields are still unanswered: "
                            f"[{missing_list}]. "
                            f"Ask the NEXT missing field: '{next_field}'. "
                            f"Check the Field Summary Table for how to ask it."
                        )))
                        continue

                logger.info(
                    "LLM returned valid JSON action: %s",
                    action or intent or "unknown",
                )
                return parsed

            logger.warning(
                "LLM returned invalid JSON (attempt %d/%d): %s",
                attempt + 1,
                MAX_JSON_RETRIES + 1,
                content[:300],
            )
            messages.append(HumanMessage(content=JSON_RETRY_PROMPT))

        except Exception as e:
            logger.error("LLM call failed (attempt %d): %s", attempt + 1, e)
            if attempt == MAX_JSON_RETRIES:
                return None

    logger.error(
        "All %d LLM attempts failed to produce valid JSON",
        MAX_JSON_RETRIES + 1,
    )
    return None

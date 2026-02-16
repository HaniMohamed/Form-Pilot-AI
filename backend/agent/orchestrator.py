"""
Markdown-driven conversation orchestrator.

The LLM reads the full markdown form context and drives the entire
conversation: field ordering, visibility, validation, and tool calls.

Flow per user message:
1. Build system prompt with markdown + current answers
2. Send conversation history to LLM
3. Parse LLM response as JSON action
4. If TOOL_CALL: return it to the frontend for execution
5. If ASK_*: track the answer and return the action
6. If FORM_COMPLETE: return the final data
"""

import json
import logging
import re
from datetime import date, datetime
from typing import Any

from dateutil import parser as dateutil_parser
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agent.prompts import (
    build_extraction_prompt,
    build_system_prompt,
    extract_field_type_map,
    extract_form_title,
    extract_required_field_ids,
    summarize_required_fields,
)
from backend.core.actions import build_message_action

logger = logging.getLogger(__name__)

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


def _extract_options_hint(tool_data: dict) -> str:
    """Try to extract human-readable option names from a tool result.

    Looks for common patterns in tool result data (arrays of objects
    with name/value fields) and returns a JSON list of option strings.
    Returns empty string if no options can be extracted.
    """
    options: list[str] = []

    for key, val in tool_data.items():
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
        return False, f"'{stripped}' is not a valid date. Please provide a date like 2026-01-15 or January 15, 2026."

    try:
        parsed = dateutil_parser.parse(stripped, dayfirst=False)
        # Extra sanity: reject dates with impossible month/day that
        # dateutil might silently swap or misparse
        if not isinstance(parsed.date(), date):
            raise ValueError
        return True, ""
    except (ValueError, TypeError, OverflowError):
        return False, f"'{stripped}' is not a valid date. Please provide a date like 2026-01-15 or January 15, 2026."


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
        return False, f"'{stripped}' is not a valid date/time. Please provide something like 2026-01-15 10:30 AM."

    try:
        parsed = dateutil_parser.parse(stripped, dayfirst=False)
        if not isinstance(parsed, datetime):
            raise ValueError
        return True, ""
    except (ValueError, TypeError, OverflowError):
        return False, f"'{stripped}' is not a valid date/time. Please provide something like 2026-01-15 10:30 AM."


def validate_time_answer(value: str) -> tuple[bool, str]:
    """Validate that a string is a recognizable time value.

    Accepts common time formats: "10 AM", "10:30", "2:45 PM", "14:00", etc.

    Args:
        value: The user-provided time string.

    Returns:
        A tuple of (is_valid, error_message).
    """
    stripped = value.strip()
    if not stripped:
        return False, "Time cannot be empty."

    # Reject strings that are purely alphabetic with no digits
    if not any(ch.isdigit() for ch in stripped):
        return False, f"'{stripped}' is not a valid time. Please provide a time like 10:30 AM or 14:00."

    # Try common time patterns
    time_patterns = [
        r"^\d{1,2}:\d{2}\s*(AM|PM|am|pm)?$",       # 10:30 AM, 14:00
        r"^\d{1,2}\s*(AM|PM|am|pm)$",                # 10 AM, 2 PM
        r"^\d{1,2}:\d{2}:\d{2}\s*(AM|PM|am|pm)?$",  # 10:30:00 AM
    ]
    for pattern in time_patterns:
        if re.match(pattern, stripped):
            return True, ""

    # Fallback: try dateutil — if it can parse a time component, accept it
    try:
        parsed = dateutil_parser.parse(stripped, dayfirst=False)
        # If it parsed successfully, it at least has a time component
        return True, ""
    except (ValueError, TypeError, OverflowError):
        pass

    return False, f"'{stripped}' is not a valid time. Please provide a time like 10:30 AM or 14:00."


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
    # Note: ASK_TEXT for time fields (e.g. injuryTime) is validated by
    # the LLM prompt, not here, since ASK_TEXT is generic.
    return True, ""


class FormOrchestrator:
    """Orchestrates a markdown-driven form-filling conversation.

    The LLM receives the full markdown as system prompt context and
    decides what to ask, when to call tools, and when the form is complete.

    Supports a two-phase flow:
    1. Greeting + bulk extraction: user provides free-text, LLM extracts values
    2. Follow-up: LLM asks for remaining fields one at a time

    Args:
        form_context_md: The markdown content describing the form.
        llm: A LangChain BaseChatModel instance.
    """

    def __init__(self, form_context_md: str, llm: BaseChatModel):
        self.form_context_md = form_context_md
        self.llm = llm
        self.answers: dict[str, Any] = {}
        self.conversation_history: list[dict[str, str]] = []
        self._initial_extraction_done: bool = False
        # Track the field currently being asked so we can auto-store
        # the user's answer deterministically (don't rely on LLM to echo it)
        self._pending_field_id: str | None = None
        # Track the action type of the pending field (e.g. ASK_DATE)
        # so we can validate the user's answer before storing
        self._pending_action_type: str | None = None
        # Track the last TOOL_CALL so we can guide the LLM after results return
        self._pending_tool_name: str | None = None
        # Extract required field IDs from the markdown for FORM_COMPLETE guard
        self._required_fields: list[str] = extract_required_field_ids(
            form_context_md
        )
        # Extract field type map (field_id -> type string) for answer validation
        self._field_types: dict[str, str] = extract_field_type_map(
            form_context_md
        )

    def get_initial_action(self) -> dict:
        """Get the first action — a friendly greeting with form name and data summary.

        Extracts the form title and required field labels from the markdown
        to build a warm, informative greeting that helps the user understand
        what data is needed upfront.

        Returns:
            A MESSAGE action dict with the greeting.
        """
        greeting = self._build_greeting()
        self._add_history("assistant", greeting)
        return build_message_action(greeting)

    def _build_greeting(self) -> str:
        """Build a friendly, conversational greeting with form name and data summary."""
        form_title = extract_form_title(self.form_context_md)
        summary = summarize_required_fields(self.form_context_md)

        if summary:
            greeting = (
                f"Hi there! I'm FormPilot AI, and I'll be helping you fill out "
                f"the **{form_title}** form.\n\n"
                f"{summary}.\n\n"
                f"Feel free to tell me everything you know in one message — "
                f"I'll extract what I can and only ask about the rest!"
            )
        else:
            greeting = (
                f"Hi there! I'm FormPilot AI, and I'll be helping you fill out "
                f"the **{form_title}** form.\n\n"
                f"Go ahead and describe all the information you have — "
                f"I'll take care of filling in the form and only ask about "
                f"anything that's missing!"
            )

        return greeting

    async def process_user_message(
        self,
        user_message: str,
        tool_results: list[dict] | None = None,
    ) -> dict:
        """Process a user message or tool results and return the next action.

        Args:
            user_message: The raw text message from the user.
            tool_results: Results from TOOL_CALL actions executed by the frontend.

        Returns:
            An action dict for the UI to render.
        """
        # If tool results are provided, add them to history with a directive
        if tool_results:
            for result in tool_results:
                tool_name = result.get("tool_name", "unknown")
                tool_data = result.get("result", {})

                # Extract option names from the result to help the LLM
                options_hint = _extract_options_hint(tool_data)

                # Add tool result + directive to history
                directive = (
                    f"[Tool result for {tool_name}]: {json.dumps(tool_data)}"
                )
                if options_hint:
                    directive += (
                        f"\n\n[INSTRUCTION: Use the data above. "
                        f"Return ASK_DROPDOWN with these options: {options_hint}]"
                    )
                else:
                    directive += (
                        "\n\n[INSTRUCTION: Use the data above to continue the form. "
                        "Return the appropriate JSON action.]"
                    )
                self._add_history("user", directive)
            self._pending_tool_name = None

        # Auto-store answer: if we were asking a field and the user responded
        # (not a tool result), validate and store their answer deterministically
        if self._pending_field_id and user_message.strip() and not tool_results:
            raw_answer = user_message.strip()
            # Validate the answer based on the action type (e.g. ASK_DATE)
            is_valid, validation_error = validate_answer_for_action(
                self._pending_action_type or "", raw_answer
            )
            if is_valid:
                self.answers[self._pending_field_id] = raw_answer
                logger.info(
                    "Auto-stored answer: %s = %s",
                    self._pending_field_id,
                    raw_answer[:100],
                )
                self._pending_field_id = None
                self._pending_action_type = None
            else:
                # Validation failed — don't store, keep pending field so
                # the LLM re-asks. Inject a validation error into history
                # so the LLM knows to ask again with a helpful message.
                logger.warning(
                    "Validation failed for %s (%s): %s",
                    self._pending_field_id,
                    self._pending_action_type,
                    validation_error,
                )
                self._add_history("user", user_message)
                self._add_history(
                    "user",
                    f"[SYSTEM: The user's answer '{raw_answer}' for field "
                    f"'{self._pending_field_id}' is INVALID. {validation_error} "
                    f"You MUST re-ask this field using {self._pending_action_type} "
                    f"with field_id '{self._pending_field_id}'. "
                    f"Tell the user their input was not valid and ask again.]",
                )
                # Don't clear _pending_field_id — the LLM will re-ask
                # Skip adding user_message again (already added above)
                return await self._process_conversation()

        # Add the user message to history (skip if empty and we have tool results)
        if user_message.strip():
            self._add_history("user", user_message)

        # Phase 1: Bulk extraction (first real user message, no tool results)
        if not self._initial_extraction_done and not tool_results:
            return await self._process_extraction(user_message)

        # Phase 2: LLM-driven conversation
        return await self._process_conversation()

    async def _process_extraction(self, user_message: str) -> dict:
        """Process the user's initial free-text and extract field values.

        Args:
            user_message: The user's free-text description.

        Returns:
            An action dict (could be ASK_*, TOOL_CALL, or MESSAGE).
        """
        self._initial_extraction_done = True

        # Call LLM with the extraction prompt
        extraction_prompt = build_extraction_prompt(self.form_context_md)

        messages = [
            SystemMessage(content=extraction_prompt),
            HumanMessage(content=user_message),
        ]

        parsed = await self._call_llm_with_retry(messages)

        if parsed is None:
            # Extraction failed — fall back to normal conversation
            return await self._process_conversation()

        # If LLM returned multi_answer, validate and store the answers
        intent = parsed.get("intent")
        if intent == "multi_answer":
            answers = parsed.get("answers", {})
            if isinstance(answers, dict):
                # Validate extracted answers before storing
                validated = {}
                rejected_fields = []
                for field_id, value in answers.items():
                    field_type = self._field_types.get(field_id, "")
                    if field_type in ("date", "datetime") and isinstance(value, str):
                        action = "ASK_DATE" if field_type == "date" else "ASK_DATETIME"
                        is_valid, err = validate_answer_for_action(action, value)
                        if not is_valid:
                            logger.warning(
                                "Extraction rejected %s = '%s': %s",
                                field_id, value, err,
                            )
                            rejected_fields.append(field_id)
                            continue
                    validated[field_id] = value
                self.answers.update(validated)

            llm_message = parsed.get("message", "")
            if llm_message:
                self._add_history("assistant", llm_message)

            # Now continue with normal conversation to get the next action
            return await self._process_conversation()

        # LLM returned a direct action — return it
        return self._finalize_action(parsed)

    async def _process_conversation(self) -> dict:
        """Run a conversation turn: send context to LLM, get next action.

        Returns:
            An action dict for the UI.
        """
        system_prompt = build_system_prompt(
            form_context_md=self.form_context_md,
            answers=self.answers,
            conversation_history=self.conversation_history,
            required_fields=self._required_fields,
        )

        messages = [SystemMessage(content=system_prompt)]

        # Include recent conversation history
        history = self.conversation_history[-MAX_HISTORY_MESSAGES:]
        for msg in history:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

        parsed = await self._call_llm_with_retry(messages)

        if parsed is None:
            action = build_message_action(
                "I'm sorry, I had trouble understanding. Could you try again?"
            )
            self._add_history("assistant", action["text"])
            return action

        return self._finalize_action(parsed)

    def _finalize_action(self, parsed: dict) -> dict:
        """Process a parsed LLM response and track state.

        Tracks the pending field for deterministic answer storage,
        and records the assistant message in conversation history.

        Args:
            parsed: The parsed JSON action from the LLM.

        Returns:
            The action dict for the UI.
        """
        action_type = parsed.get("action", "")
        field_id = parsed.get("field_id")

        # If the LLM explicitly set a field value, store it
        value = parsed.get("value")
        if field_id and value is not None:
            self.answers[field_id] = value

        # Track which field is being asked — the user's next message
        # will be auto-stored as the answer for this field
        if action_type.startswith("ASK_") and field_id:
            self._pending_field_id = field_id
            self._pending_action_type = action_type
            self._pending_tool_name = None
            logger.info("Now asking field: %s (type: %s)", field_id, action_type)
        elif action_type == "TOOL_CALL":
            self._pending_tool_name = parsed.get("tool_name")
            self._pending_field_id = None
            self._pending_action_type = None
            logger.info("Pending tool call: %s", self._pending_tool_name)
        else:
            self._pending_field_id = None
            self._pending_action_type = None
            self._pending_tool_name = None

        # If FORM_COMPLETE, make sure we have the data
        if action_type == "FORM_COMPLETE":
            data = parsed.get("data")
            if isinstance(data, dict):
                self.answers.update(data)
            # Ensure the data field is populated
            if "data" not in parsed or not parsed["data"]:
                parsed["data"] = dict(self.answers)

        # Record assistant message in history
        msg = parsed.get("message") or parsed.get("text", "")
        if msg:
            self._add_history("assistant", msg)

        return parsed

    # -----------------------------------------------------------------
    # LLM interaction
    # -----------------------------------------------------------------

    async def _call_llm_with_retry(self, messages: list) -> dict | None:
        """Call the LLM and parse its JSON response, with retries.

        Args:
            messages: The message list to send to the LLM.

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
                response = await self.llm.ainvoke(messages)
                content = response.content.strip()

                logger.debug("LLM raw response (first 500 chars): %s", content[:500])

                parsed = self._extract_json(content)
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
                        and asked_field in self.answers
                    ):
                        logger.warning(
                            "LLM re-asked already answered field '%s' — "
                            "retrying for next field",
                            asked_field,
                        )
                        answered = ", ".join(self.answers.keys())
                        messages.append(HumanMessage(content=(
                            f"WRONG. The field '{asked_field}' is already answered. "
                            f"Already answered fields: [{answered}]. "
                            "Ask the NEXT unanswered field instead."
                        )))
                        continue

                    # Catch MESSAGE during active form filling —
                    # the model is asking a question without using ASK_* format,
                    # which means _pending_field_id won't be set and answers
                    # won't be tracked. Retry once to get proper ASK_* action.
                    if (
                        action == "MESSAGE"
                        and self._initial_extraction_done
                        and self.answers
                        and not parsed.get("field_id")
                    ):
                        # Only retry this once to avoid infinite loops
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
                            answered = ", ".join(self.answers.keys())
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

                    # Catch premature FORM_COMPLETE — the model thinks it's done
                    # but required fields are still missing
                    if action == "FORM_COMPLETE" and self._required_fields:
                        missing = [
                            fid for fid in self._required_fields
                            if fid not in self.answers
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

        logger.error("All %d LLM attempts failed to produce valid JSON", MAX_JSON_RETRIES + 1)
        return None

    def _extract_json(self, content: str) -> dict | None:
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

    # -----------------------------------------------------------------
    # History management
    # -----------------------------------------------------------------

    def _add_history(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        self.conversation_history.append({"role": role, "content": content})

    def get_answers(self) -> dict[str, Any]:
        """Return the current collected answers."""
        return dict(self.answers)

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
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agent.prompts import build_extraction_prompt, build_system_prompt
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

    def get_initial_action(self) -> dict:
        """Get the first action — a greeting asking the user to describe their data.

        Returns:
            A MESSAGE action dict with the greeting.
        """
        greeting = (
            "Hello! I'm FormPilot AI, your form-filling assistant. "
            "Please describe all the information you'd like to fill in, "
            "and I'll take care of the rest. You can tell me everything at once!"
        )
        self._add_history("assistant", greeting)
        return build_message_action(greeting)

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
        # If tool results are provided, add them to history
        if tool_results:
            for result in tool_results:
                tool_name = result.get("tool_name", "unknown")
                tool_data = result.get("result", {})
                self._add_history(
                    "user",
                    f"[Tool result for {tool_name}]: {json.dumps(tool_data)}",
                )

        # Auto-store answer: if we were asking a field and the user responded
        # (not a tool result), store their answer deterministically
        if self._pending_field_id and user_message.strip() and not tool_results:
            self.answers[self._pending_field_id] = user_message.strip()
            logger.info(
                "Auto-stored answer: %s = %s",
                self._pending_field_id,
                user_message.strip()[:100],
            )
            self._pending_field_id = None

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

        # If LLM returned multi_answer, store the answers
        intent = parsed.get("intent")
        if intent == "multi_answer":
            answers = parsed.get("answers", {})
            if isinstance(answers, dict):
                self.answers.update(answers)

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
            logger.info("Now asking field: %s", field_id)
        else:
            self._pending_field_id = None

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

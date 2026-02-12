"""
Conversation orchestrator for form filling.

This is the main entry point that coordinates:
- FormStateManager (state, visibility, validation)
- LLM (intent detection, natural language understanding)
- Action protocol (structured output to the UI)

Flow per user message:
1. Build context-aware prompt with current form state
2. Send to LLM to interpret the user's message
3. Based on LLM intent: store answer, handle correction, or clarify
4. Return the next action (ASK_* or FORM_COMPLETE) to the UI
"""

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from backend.agent.prompts import build_extraction_prompt, build_system_prompt, build_user_message
from backend.core.actions import (
    build_action_for_field,
    build_completion_payload,
    build_extraction_summary_action,
    build_message_action,
)
from backend.core.form_state import AnswerValidationError, FormStateManager

logger = logging.getLogger(__name__)

# Maximum retries when LLM returns invalid JSON
MAX_JSON_RETRIES = 2

# Corrective prompt sent when LLM output is not valid JSON
JSON_RETRY_PROMPT = (
    "Your previous response was not valid JSON. "
    "You MUST respond with a valid JSON object. "
    "Do not include any text outside the JSON object. "
    "Try again."
)


class FormOrchestrator:
    """Orchestrates a single form-filling conversation.

    Coordinates between the LLM, form state manager, and action protocol
    to guide the user through form completion one field at a time.

    Supports a two-phase flow:
    1. Greeting + bulk extraction: user provides free-text, LLM extracts all possible values
    2. Follow-up: ask for remaining missing fields one at a time

    Args:
        state_manager: An initialized FormStateManager with the form schema.
        llm: A LangChain BaseChatModel instance.
    """

    def __init__(self, state_manager: FormStateManager, llm: BaseChatModel):
        self.state = state_manager
        self.llm = llm
        # Tracks whether the initial bulk extraction has been processed
        self._initial_extraction_done: bool = False

    def get_initial_action(self) -> dict:
        """Get the first action to send to the UI.

        Returns a greeting MESSAGE asking the user to describe all their
        form data in one go (instead of immediately asking for the first field).

        Returns:
            A MESSAGE action dict with the greeting.
        """
        if self.state.is_complete():
            return build_completion_payload(self.state.get_visible_answers())

        greeting = (
            "Hello! I'm FormPilot AI, your form-filling assistant. "
            "Please describe all the information you'd like to fill in, "
            "and I'll take care of the rest. You can tell me everything at once!"
        )
        action = build_message_action(greeting)

        # Record in conversation history
        self.state.add_message("assistant", greeting)

        return action

    async def process_user_message(self, user_message: str) -> dict:
        """Process a user message and return the next action.

        This is the main entry point for each conversation turn.
        Routes to extraction phase or one-at-a-time phase based on state.

        Args:
            user_message: The raw text message from the user.

        Returns:
            An action dict for the UI to render.
        """
        # Record the user message
        self.state.add_message("user", user_message)

        # If form is already complete, return completion
        if self.state.is_complete():
            return self._handle_form_complete()

        # Phase 1: Bulk extraction (first user message)
        if not self._initial_extraction_done:
            return await self._process_extraction(user_message)

        # Phase 2: One-at-a-time follow-up
        return await self._process_one_at_a_time(user_message)

    async def _process_extraction(self, user_message: str) -> dict:
        """Process the user's initial free-text and extract field values in bulk.

        Args:
            user_message: The user's free-text description.

        Returns:
            An action dict (summary + next missing field, or FORM_COMPLETE).
        """
        # Mark extraction as done regardless of outcome
        self._initial_extraction_done = True

        # Call LLM with the extraction prompt
        llm_response = await self._call_extraction_llm(user_message)

        if llm_response is None:
            # LLM failed — fall back to one-at-a-time from the start
            next_field = self.state.get_next_field()
            if next_field is None:
                return self._handle_form_complete()
            action = build_action_for_field(next_field)
            action["message"] = (
                "I had trouble processing your description. "
                f"Let's go through the form step by step. {next_field.prompt}"
            )
            self.state.add_message("assistant", action["message"])
            return action

        # Handle the multi_answer response
        return self._handle_multi_answer(llm_response)

    async def _process_one_at_a_time(self, user_message: str) -> dict:
        """Process a user message in the one-at-a-time follow-up phase.

        Args:
            user_message: The user's message.

        Returns:
            An action dict for the UI.
        """
        # Get current context
        next_field = self.state.get_next_field()
        if next_field is None:
            return self._handle_form_complete()

        # Call the LLM to interpret the user's message
        llm_response = await self._call_llm(user_message)

        if llm_response is None:
            return self._build_response_with_action(
                build_message_action(
                    "I'm sorry, I had trouble understanding. Could you try again?"
                )
            )

        # Process the LLM's interpreted intent
        return self._process_llm_response(llm_response, next_field)

    def process_user_message_sync(self, user_message: str) -> dict:
        """Synchronous wrapper for process_user_message.

        Useful for testing and simple integrations.
        """
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.process_user_message(user_message))
        finally:
            loop.close()

    # -----------------------------------------------------------------
    # Multi-answer handling (bulk extraction)
    # -----------------------------------------------------------------

    def _handle_multi_answer(self, llm_response: dict) -> dict:
        """Handle a multi_answer intent from bulk extraction.

        Validates and stores each extracted answer, then returns a summary
        action with the next missing field (or FORM_COMPLETE).

        Args:
            llm_response: Parsed JSON from the LLM with multi_answer intent.

        Returns:
            An action dict for the UI.
        """
        answers = llm_response.get("answers", {})
        llm_message = llm_response.get("message", "")

        if not isinstance(answers, dict):
            # LLM returned bad format — fall back
            next_field = self.state.get_next_field()
            if next_field is None:
                return self._handle_form_complete()
            action = build_action_for_field(next_field)
            action["message"] = f"Let me ask you about each field. {next_field.prompt}"
            self.state.add_message("assistant", action["message"])
            return action

        # Bulk-set the answers
        accepted, rejected = self.state.set_answers_bulk(answers)

        # Determine next action
        next_field = self.state.get_next_field()
        visible_answers = self.state.get_visible_answers() if next_field is None else None

        action = build_extraction_summary_action(
            accepted=accepted,
            rejected=rejected,
            next_field=next_field,
            visible_answers=visible_answers,
            llm_message=llm_message,
        )

        # Record in conversation history
        msg = action.get("message") or action.get("text", "")
        if msg:
            self.state.add_message("assistant", msg)

        return action

    # -----------------------------------------------------------------
    # LLM interaction
    # -----------------------------------------------------------------

    async def _call_extraction_llm(self, user_message: str) -> dict | None:
        """Call the LLM with the extraction prompt and parse its response.

        Args:
            user_message: The user's free-text description.

        Returns:
            Parsed JSON dict with multi_answer intent, or None if fails.
        """
        extraction_prompt = build_extraction_prompt(self.state.schema)

        messages = [
            SystemMessage(content=extraction_prompt),
            HumanMessage(content=user_message),
        ]

        for attempt in range(MAX_JSON_RETRIES + 1):
            try:
                response = await self.llm.ainvoke(messages)
                content = response.content.strip()
                parsed = self._extract_json(content)
                if parsed is not None:
                    return parsed

                logger.warning(
                    "Extraction LLM returned invalid JSON (attempt %d): %s",
                    attempt + 1,
                    content[:200],
                )
                messages.append(HumanMessage(content=JSON_RETRY_PROMPT))

            except Exception as e:
                logger.error("Extraction LLM call failed (attempt %d): %s", attempt + 1, e)
                if attempt == MAX_JSON_RETRIES:
                    return None

        return None

    async def _call_llm(self, user_message: str) -> dict | None:
        """Call the LLM and parse its JSON response, with retries.

        Args:
            user_message: The user's raw message.

        Returns:
            Parsed JSON dict from the LLM, or None if all retries fail.
        """
        # Build the system prompt with full context
        system_prompt = build_system_prompt(
            schema=self.state.schema,
            answers=self.state.get_all_answers(),
            next_field=self.state.get_next_field(),
            visible_fields=self.state.get_visible_fields(),
        )

        messages = [
            SystemMessage(content=system_prompt),
        ]

        # Include recent conversation history for context (last 10 messages)
        history = self.state.get_conversation_history()
        recent = history[-10:] if len(history) > 10 else history
        for msg in recent:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))

        # Attempt to get valid JSON from the LLM
        for attempt in range(MAX_JSON_RETRIES + 1):
            try:
                response = await self.llm.ainvoke(messages)
                content = response.content.strip()
                parsed = self._extract_json(content)
                if parsed is not None:
                    return parsed

                # Invalid JSON — add retry prompt
                logger.warning(
                    "LLM returned invalid JSON (attempt %d): %s",
                    attempt + 1,
                    content[:200],
                )
                messages.append(HumanMessage(content=JSON_RETRY_PROMPT))

            except Exception as e:
                logger.error("LLM call failed (attempt %d): %s", attempt + 1, e)
                if attempt == MAX_JSON_RETRIES:
                    return None

        return None

    def _extract_json(self, content: str) -> dict | None:
        """Extract a JSON object from LLM output.

        Handles cases where the LLM wraps JSON in markdown code fences.

        Args:
            content: Raw LLM output string.

        Returns:
            Parsed dict, or None if extraction fails.
        """
        # Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code fence
        if "```" in content:
            # Find content between first ``` and last ```
            parts = content.split("```")
            for part in parts:
                # Strip optional language tag (e.g., "json\n")
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
    # Response processing
    # -----------------------------------------------------------------

    def _process_llm_response(self, llm_response: dict, next_field) -> dict:
        """Process the parsed LLM response based on its intent.

        Args:
            llm_response: Parsed JSON from the LLM.
            next_field: The current field expecting an answer.

        Returns:
            An action dict for the UI.
        """
        intent = llm_response.get("intent", "ask")
        message = llm_response.get("message", "")

        match intent:
            case "answer":
                return self._handle_answer(llm_response, next_field, message)
            case "correction":
                return self._handle_correction(llm_response, message)
            case "clarify":
                return self._handle_clarify(message, next_field)
            case "ask":
                return self._handle_ask(message, next_field)
            case _:
                # Unknown intent — treat as clarify
                return self._handle_clarify(message, next_field)

    def _handle_answer(self, llm_response: dict, next_field, message: str) -> dict:
        """Handle an answer intent from the LLM.

        Validates and stores the answer, then returns the next action.
        """
        field_id = llm_response.get("field_id", next_field.id)
        value = llm_response.get("value")

        if value is None:
            # LLM said "answer" but no value — ask again
            action = build_action_for_field(next_field)
            action["message"] = message or f"I need a value for {next_field.id}. {next_field.prompt}"
            self.state.add_message("assistant", action["message"])
            return action

        try:
            self.state.set_answer(field_id, value)
        except AnswerValidationError as e:
            # Invalid answer — tell the user and re-ask
            error_msg = message or str(e)
            action = build_action_for_field(next_field)
            action["message"] = f"That doesn't look right: {e.message}. Please try again."
            self.state.add_message("assistant", action["message"])
            return action
        except ValueError:
            # Field doesn't exist — re-ask current field
            action = build_action_for_field(next_field)
            action["message"] = message or next_field.prompt
            self.state.add_message("assistant", action["message"])
            return action

        # Answer accepted — check if form is complete
        if self.state.is_complete():
            return self._handle_form_complete(message)

        # Get the next field
        new_next = self.state.get_next_field()
        if new_next is None:
            return self._handle_form_complete(message)

        action = build_action_for_field(new_next)
        action["message"] = message or f"Got it! {new_next.prompt}"
        self.state.add_message("assistant", action["message"])
        return action

    def _handle_correction(self, llm_response: dict, message: str) -> dict:
        """Handle a correction intent — clear the specified field and re-ask."""
        field_id = llm_response.get("field_id")

        if field_id and self.state.get_answer(field_id) is not None:
            self.state.clear_answer(field_id)

            # Find the field to re-ask
            field = self.state._get_field_by_id(field_id)
            if field:
                action = build_action_for_field(field)
                action["message"] = message or f"No problem! Let's update {field_id}. {field.prompt}"
                self.state.add_message("assistant", action["message"])
                return action

        # Couldn't find the field to correct — ask next field
        next_field = self.state.get_next_field()
        if next_field:
            action = build_action_for_field(next_field)
            action["message"] = message or "I'm not sure which answer to change. Let's continue."
            self.state.add_message("assistant", action["message"])
            return action

        return self._handle_form_complete(message)

    def _handle_clarify(self, message: str, next_field) -> dict:
        """Handle a clarification — re-present the current field."""
        action = build_action_for_field(next_field)
        action["message"] = message or next_field.prompt
        self.state.add_message("assistant", action["message"])
        return action

    def _handle_ask(self, message: str, next_field) -> dict:
        """Handle an ask intent — present the current/next field question."""
        action = build_action_for_field(next_field)
        action["message"] = message or next_field.prompt
        self.state.add_message("assistant", action["message"])
        return action

    def _handle_form_complete(self, message: str = "") -> dict:
        """Build and return the FORM_COMPLETE action."""
        payload = build_completion_payload(self.state.get_visible_answers())
        payload["message"] = message or "All fields are complete! Here's a summary of your answers."
        self.state.add_message("assistant", payload["message"])
        return payload

    def _build_response_with_action(self, action: dict) -> dict:
        """Helper to record action message and return it."""
        if "message" in action:
            self.state.add_message("assistant", action.get("message", ""))
        elif "text" in action:
            self.state.add_message("assistant", action["text"])
        return action

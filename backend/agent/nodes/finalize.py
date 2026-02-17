"""
Finalize node — post-processes the LLM response and tracks state.

Resolves pending text answers awaiting LLM contextual validation,
tracks the new pending field for deterministic answer storage,
handles FORM_COMPLETE data, and records the assistant message.
"""

import logging

from backend.agent.state import FormPilotState

logger = logging.getLogger(__name__)


def finalize_node(state: FormPilotState) -> dict:
    """Process a parsed LLM response and track conversation state.

    Handles:
    - Resolving pending text answers (LLM accepted or rejected)
    - Storing explicit field values from the LLM
    - Tracking which field is currently being asked
    - Populating FORM_COMPLETE data
    - Recording the assistant message in history

    Returns:
        Partial state with finalized action and updated tracking fields.
    """
    parsed = state.get("parsed_llm_response")
    if parsed is None:
        # Should not reach here if routing is correct, but handle gracefully
        return {}

    pending_text_value = state.get("pending_text_value")
    pending_text_field_id = state.get("pending_text_field_id")
    current_answers = dict(state.get("answers", {}))

    action_type = parsed.get("action", "")
    field_id = parsed.get("field_id")

    answers_update: dict = {}
    history_entries: list[dict[str, str]] = []
    updates: dict = {}

    # --- Resolve pending text answer (LLM contextual validation) ---
    # If we were holding a text answer for LLM validation, check whether
    # the LLM accepted it (moved to a different field) or rejected it
    # (re-asked the same field).
    if pending_text_value and pending_text_field_id:
        is_reask = (
            action_type.startswith("ASK_")
            and field_id == pending_text_field_id
        )
        if is_reask:
            logger.info(
                "LLM rejected text answer for '%s' — discarding",
                pending_text_field_id,
            )
        else:
            # LLM accepted — commit the held answer
            answers_update[pending_text_field_id] = pending_text_value
            logger.info(
                "LLM accepted text answer: %s = %s",
                pending_text_field_id,
                pending_text_value[:100],
            )
        # Clear the pending text state regardless
        updates["pending_text_value"] = None
        updates["pending_text_field_id"] = None

    # If the LLM explicitly set a field value, store it
    value = parsed.get("value")
    if field_id and value is not None:
        answers_update[field_id] = value

    # Track which field is being asked — the user's next message
    # will be auto-stored as the answer for this field
    if action_type.startswith("ASK_") and field_id:
        updates["pending_field_id"] = field_id
        updates["pending_action_type"] = action_type
        updates["pending_tool_name"] = None
        logger.info("Now asking field: %s (type: %s)", field_id, action_type)
    elif action_type == "TOOL_CALL":
        updates["pending_tool_name"] = parsed.get("tool_name")
        updates["pending_field_id"] = None
        updates["pending_action_type"] = None
        logger.info("Pending tool call: %s", updates["pending_tool_name"])
    else:
        updates["pending_field_id"] = None
        updates["pending_action_type"] = None
        updates["pending_tool_name"] = None

    # If FORM_COMPLETE, make sure we have the data
    if action_type == "FORM_COMPLETE":
        data = parsed.get("data")
        if isinstance(data, dict):
            answers_update.update(data)
        # Ensure the data field is populated with all answers
        merged_answers = dict(current_answers)
        merged_answers.update(answers_update)
        if "data" not in parsed or not parsed["data"]:
            parsed["data"] = merged_answers

    # Record assistant message in history
    msg = parsed.get("message") or parsed.get("text", "")
    if msg:
        history_entries.append({"role": "assistant", "content": msg})

    updates["action"] = parsed
    if answers_update:
        updates["answers"] = answers_update
    if history_entries:
        updates["conversation_history"] = history_entries

    return updates

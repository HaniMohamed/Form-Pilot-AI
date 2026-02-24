"""
Finalize node — post-processes the LLM response and tracks state.

Resolves pending text answers awaiting LLM contextual validation,
tracks the new pending field for deterministic answer storage,
handles FORM_COMPLETE data, and records the assistant message.
"""

import logging
import re

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
    required_by_step = state.get("required_fields_by_step", {})
    current_step = state.get("current_step", 1)
    max_step = state.get("max_step", 1)
    completed_steps = set(state.get("completed_steps", []))
    field_prompt_map = state.get("field_prompt_map", {})

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
    updates["allow_answered_field_update"] = False
    if answers_update:
        updates["answers"] = answers_update
    if history_entries:
        updates["conversation_history"] = history_entries

    # --- Step checkpoint (human-in-the-loop) ---
    # In multi-step forms, after collecting all required fields for the
    # current step, pause and ask the user to confirm before moving on.
    merged_answers = dict(current_answers)
    merged_answers.update(answers_update)
    step_required = required_by_step.get(current_step, [])
    is_multi_step = bool(required_by_step) and max_step > 1
    step_complete = bool(step_required) and all(fid in merged_answers for fid in step_required)
    is_last_step = current_step >= max_step

    if (
        is_multi_step
        and step_complete
        and current_step not in completed_steps
        and not is_last_step
    ):
        summary_text = _build_step_summary(
            step=current_step,
            field_ids=step_required,
            answers=merged_answers,
            field_prompt_map=field_prompt_map,
        )
        updates["action"] = {"action": "MESSAGE", "text": summary_text}
        updates["pending_field_id"] = None
        updates["pending_action_type"] = None
        updates["pending_tool_name"] = None
        updates["awaiting_step_confirmation"] = True
        updates["conversation_history"] = [{"role": "assistant", "content": summary_text}]

    return updates


def _build_step_summary(
    step: int,
    field_ids: list[str],
    answers: dict,
    field_prompt_map: dict[str, str],
) -> str:
    lines = [f"Step {step} is complete. Here is a quick summary:"]
    for field_id in field_ids:
        label = field_prompt_map.get(field_id) or _field_id_to_label(field_id)
        value = answers.get(field_id, "")
        lines.append(f"- {label}: {value}")
    lines.append(
        "Please confirm to continue to the next step, "
        "or tell me what you want to change in this step."
    )
    return "\n".join(lines)


def _field_id_to_label(field_id: str) -> str:
    # Convert camelCase/snake_case IDs to readable labels.
    words = field_id.replace("_", " ")
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", words)
    return words.strip().capitalize()

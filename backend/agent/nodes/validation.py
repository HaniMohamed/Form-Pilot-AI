"""
Validate input node — validates user answers for pending fields.

Two validation strategies:
1. Format validation (ASK_DATE, ASK_DATETIME): deterministic check before
   storing — reject immediately if format is wrong.
2. Context validation (ASK_TEXT): hold the answer and let the LLM judge
   if it's relevant. The LLM either accepts (moves to next field) or
   rejects (re-asks same field).
"""

import logging

from backend.agent.state import FormPilotState
from backend.agent.utils import validate_answer_for_action

logger = logging.getLogger(__name__)


def validate_input_node(state: FormPilotState) -> dict:
    """Validate the user's answer for the currently pending field.

    Returns:
        Partial state with validation results. Always routes to conversation
        afterward — the LLM handles re-asking on error.
    """
    user_message = state.get("user_message", "")
    pending_field_id = state.get("pending_field_id")
    pending_action_type = state.get("pending_action_type")
    raw_answer = user_message.strip()

    history_entries: list[dict[str, str]] = []
    answers_update: dict = {}
    updates: dict = {"user_message_added": True}

    if pending_action_type == "ASK_TEXT":
        # --- Context validation path (LLM decides) ---
        # Don't store yet — hold the value for LLM validation.
        logger.info(
            "Holding text answer for LLM validation: %s = %s",
            pending_field_id,
            raw_answer[:100],
        )
        history_entries.append({"role": "user", "content": user_message})
        history_entries.append({
            "role": "user",
            "content": (
                f"[SYSTEM: The user answered '{raw_answer}' for field "
                f"'{pending_field_id}'. "
                f"VALIDATE this answer: Is it relevant and appropriate for "
                f"the question asked? Does it make sense in context? "
                f"If YES — proceed to the NEXT unanswered field. "
                f"If NO (gibberish, irrelevant, nonsensical, or clearly "
                f"wrong context) — re-ask the SAME field "
                f"'{pending_field_id}' using ASK_TEXT. "
                f"Politely tell the user why their answer doesn't fit "
                f"and ask again in a clearer way.]"
            ),
        })
        updates.update({
            "pending_text_value": raw_answer,
            "pending_text_field_id": pending_field_id,
            "pending_field_id": None,
            "pending_action_type": None,
        })
    else:
        # --- Format validation path (deterministic check) ---
        is_valid, validation_error = validate_answer_for_action(
            pending_action_type or "", raw_answer
        )
        if is_valid:
            answers_update[pending_field_id] = raw_answer
            logger.info(
                "Auto-stored answer: %s = %s",
                pending_field_id,
                raw_answer[:100],
            )
            # Add user message to history (matches original fall-through behavior)
            history_entries.append({"role": "user", "content": user_message})
            updates.update({
                "pending_field_id": None,
                "pending_action_type": None,
            })
        else:
            # Validation failed — keep pending field, inject error directive
            logger.warning(
                "Validation failed for %s (%s): %s",
                pending_field_id,
                pending_action_type,
                validation_error,
            )
            history_entries.append({"role": "user", "content": user_message})
            history_entries.append({
                "role": "user",
                "content": (
                    f"[SYSTEM: The user's answer '{raw_answer}' for field "
                    f"'{pending_field_id}' is INVALID. "
                    f"{validation_error} "
                    f"You MUST re-ask this field using "
                    f"{pending_action_type} "
                    f"with field_id '{pending_field_id}'. "
                    f"Tell the user their input was not valid and "
                    f"ask again.]"
                ),
            })
            # Don't clear pending_field_id — the LLM will re-ask

    updates["conversation_history"] = history_entries
    if answers_update:
        updates["answers"] = answers_update

    return updates

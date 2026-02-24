"""
Step confirmation node — human-in-the-loop checkpoint between steps.

When a step is complete, the user must confirm before the assistant moves
to the next step. The user can also request updates to items in that step.
"""

import re

from backend.agent.state import FormPilotState
from backend.core.actions import build_message_action


_CONFIRM_WORDS = {
    "yes", "ok", "okay", "confirm", "confirmed", "continue", "proceed",
    "looks good", "all good", "correct", "approved",
    "نعم", "ايوه", "ايوا", "تمام", "موافق", "اكمل", "استمر",
}

_EDIT_WORDS = {
    "change", "update", "edit", "modify", "fix", "wrong", "not correct",
    "تعديل", "غير", "غيّر", "عدل", "صحح", "خطأ", "مو صحيح",
}


def step_confirmation_node(state: FormPilotState) -> dict:
    """Handle user reply while waiting for step confirmation."""
    user_message = state.get("user_message", "").strip()
    current_step = state.get("current_step", 1)
    required_by_step = state.get("required_fields_by_step", {})
    step_fields = required_by_step.get(current_step, [])
    text = user_message.lower()

    updates: dict = {
        "user_message_added": True,
        "conversation_history": [{"role": "user", "content": user_message}],
        "skip_conversation_turn": False,
    }

    if _is_confirm(text):
        completed = list(state.get("completed_steps", []))
        if current_step not in completed:
            completed.append(current_step)

        updates["completed_steps"] = completed
        updates["awaiting_step_confirmation"] = False
        updates["allow_answered_field_update"] = False
        updates["pending_field_id"] = None
        updates["pending_action_type"] = None
        if current_step < state.get("max_step", 1):
            updates["current_step"] = current_step + 1

        # Add lightweight directive so conversation naturally starts next step.
        updates["conversation_history"] = updates["conversation_history"] + [{
            "role": "user",
            "content": (
                f"[SYSTEM: The user confirmed Step {current_step}. "
                "Proceed to the next step now. Ask the next required unanswered field.]"
            ),
        }]
        return updates

    if _is_edit_request(text):
        updates["awaiting_step_confirmation"] = False
        updates["allow_answered_field_update"] = True
        updates["pending_field_id"] = None
        updates["pending_action_type"] = None

        field_prompt_map = state.get("field_prompt_map", {})
        field_types = state.get("field_types", {})
        requested_field = _infer_requested_field(
            text=text,
            step_fields=step_fields,
            field_prompt_map=field_prompt_map,
        )
        if requested_field:
            action_type = _action_for_field_type(field_types.get(requested_field, "text"))
            prompt_text = field_prompt_map.get(
                requested_field, f"Please share the updated value for {requested_field}."
            )
            ask_message = f"Sure, let's update that. {prompt_text}"
            updates["action"] = {
                "action": action_type,
                "field_id": requested_field,
                "label": prompt_text,
                "message": ask_message,
            }
            updates["pending_field_id"] = requested_field
            updates["pending_action_type"] = action_type
            updates["skip_conversation_turn"] = True
            updates["conversation_history"] = updates["conversation_history"] + [
                {"role": "assistant", "content": ask_message}
            ]
            return updates

        updates["conversation_history"] = updates["conversation_history"] + [{
            "role": "user",
            "content": (
                f"[SYSTEM: The user requested changes before confirming Step {current_step}. "
                f"Step {current_step} fields: {step_fields}. "
                "Help them update the requested item. Do NOT move to the next step yet. "
                "Once Step "
                f"{current_step} is complete again, provide a new summary and ask for confirmation.]"
            ),
        }]
        return updates

    # Unclear answer — keep waiting for explicit confirm or edit request.
    msg = (
        f"Step {current_step} is ready. Please confirm to continue, "
        "or tell me what you'd like to update in this step."
    )
    updates["action"] = build_message_action(msg)
    updates["allow_answered_field_update"] = False
    updates["conversation_history"] = updates["conversation_history"] + [
        {"role": "assistant", "content": msg}
    ]
    updates["skip_conversation_turn"] = True
    return updates


def _is_confirm(text: str) -> bool:
    return any(_has_token(text, token) for token in _CONFIRM_WORDS)


def _is_edit_request(text: str) -> bool:
    return any(_has_token(text, token) for token in _EDIT_WORDS)


def _has_token(text: str, token: str) -> bool:
    # For short latin words, use word boundaries (avoids "my" matching "y").
    if token.isascii() and token.isalpha() and len(token) <= 3:
        return re.search(rf"\b{re.escape(token)}\b", text) is not None
    return token in text


def _infer_requested_field(
    text: str,
    step_fields: list[str],
    field_prompt_map: dict[str, str],
) -> str | None:
    for field_id in step_fields:
        if field_id.lower() in text:
            return field_id
        label = field_prompt_map.get(field_id, "").lower()
        if label and any(word in text for word in _important_words(label)):
            return field_id
    return None


def _important_words(label: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]{4,}", label)
    return [w for w in words if w not in {"please", "provide", "share"}]


def _action_for_field_type(field_type: str) -> str:
    field_type = (field_type or "").lower()
    if field_type == "date":
        return "ASK_DATE"
    if field_type == "datetime":
        return "ASK_DATETIME"
    if field_type == "location":
        return "ASK_LOCATION"
    return "ASK_TEXT"

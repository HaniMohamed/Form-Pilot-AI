"""
Extraction node — bulk extraction from the user's initial free-text.

Calls the LLM with the extraction prompt to parse multiple field values
from a single message. Validates extracted date/datetime answers before
storing them.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from backend.agent.prompts import build_extraction_prompt
from backend.agent.state import FormPilotState
from backend.agent.utils import call_llm_with_retry, validate_answer_for_action

logger = logging.getLogger(__name__)


async def extraction_node(state: FormPilotState) -> dict:
    """Extract field values from the user's free-text description.

    If the LLM returns a multi_answer response, stores the extracted
    answers and routes to conversation for the next field. If the LLM
    returns a direct action (ASK_*, TOOL_CALL), routes to finalize.

    Returns:
        Partial state with extracted answers and extraction phase flag.
    """
    form_context_md = state["form_context_md"]
    user_message = state.get("user_message", "")
    llm = state["llm"]
    field_types = state.get("field_types", {})
    answers = dict(state.get("answers", {}))
    required_fields = state.get("required_fields", [])

    # Add user message to history
    history_entries: list[dict[str, str]] = []
    if user_message.strip():
        history_entries.append({"role": "user", "content": user_message})

    updates: dict = {
        "initial_extraction_done": True,
        "user_message_added": True,
        "conversation_history": history_entries,
        "parsed_llm_response": None,
    }

    # Build extraction prompt and call LLM
    extraction_prompt = build_extraction_prompt(form_context_md)
    messages = [
        SystemMessage(content=extraction_prompt),
        HumanMessage(content=user_message),
    ]

    parsed = await call_llm_with_retry(
        llm=llm,
        messages=messages,
        answers=answers,
        initial_extraction_done=True,
        required_fields=required_fields,
    )

    if parsed is None:
        # Extraction failed — route to conversation as fallback
        return updates

    # If LLM returned multi_answer, validate and store the answers
    intent = parsed.get("intent")
    if intent == "multi_answer":
        extracted = parsed.get("answers", {})
        if isinstance(extracted, dict):
            validated = {}
            for field_id, value in extracted.items():
                field_type = field_types.get(field_id, "")
                if field_type in ("date", "datetime") and isinstance(value, str):
                    action = "ASK_DATE" if field_type == "date" else "ASK_DATETIME"
                    is_valid, err = validate_answer_for_action(action, value)
                    if not is_valid:
                        logger.warning(
                            "Extraction rejected %s = '%s': %s",
                            field_id, value, err,
                        )
                        continue
                validated[field_id] = value

            if validated:
                updates["answers"] = validated

        llm_message = parsed.get("message", "")
        if llm_message:
            updates["conversation_history"] = (
                updates.get("conversation_history", [])
                + [{"role": "assistant", "content": llm_message}]
            )

        # Route to conversation for the next field action
        return updates

    # LLM returned a direct action — route to finalize
    updates["parsed_llm_response"] = parsed
    return updates

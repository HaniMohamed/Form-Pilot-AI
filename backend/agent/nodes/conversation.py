"""
Conversation node — runs an LLM conversation turn.

Builds the system prompt with form context and current answers,
constructs the LangChain message list from conversation history,
and calls the LLM with retry logic and guard validation.
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agent.prompts import build_system_prompt
from backend.agent.state import FormPilotState
from backend.agent.utils import MAX_HISTORY_MESSAGES, call_llm_with_retry
from backend.core.actions import build_message_action

logger = logging.getLogger(__name__)


async def conversation_node(state: FormPilotState) -> dict:
    """Run a conversation turn: send context to LLM, get next action.

    If the user message hasn't been added to history by a prior node,
    this node adds it. Then builds the full prompt context and calls the LLM.

    Sets parsed_llm_response for the finalize node, or sets action directly
    if the LLM call fails entirely.

    Returns:
        Partial state with LLM response or fallback action.
    """
    form_context_md = state["form_context_md"]
    user_message = state.get("user_message", "")
    llm = state["llm"]
    answers = dict(state.get("answers", {}))
    conversation_history = list(state.get("conversation_history", []))
    required_fields = state.get("required_fields", [])
    initial_extraction_done = state.get("initial_extraction_done", False)
    user_message_added = state.get("user_message_added", False)

    history_entries: list[dict[str, str]] = []

    # Add user message to history if not already added by a prior node
    if not user_message_added and user_message.strip():
        history_entries.append({"role": "user", "content": user_message})

    # Build the combined history (existing + newly added entries)
    # for constructing the LLM message list
    full_history = conversation_history + history_entries

    # Build system prompt with form context and current state
    system_prompt = build_system_prompt(
        form_context_md=form_context_md,
        answers=answers,
        conversation_history=full_history,
        required_fields=required_fields,
    )

    messages = [SystemMessage(content=system_prompt)]

    # Include recent conversation history as LangChain messages
    recent_history = full_history[-MAX_HISTORY_MESSAGES:]
    for msg in recent_history:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    # Call LLM with retry and guard validation
    parsed = await call_llm_with_retry(
        llm=llm,
        messages=messages,
        answers=answers,
        initial_extraction_done=initial_extraction_done,
        required_fields=required_fields,
    )

    updates: dict = {
        "user_message_added": True,
        "conversation_history": history_entries,
    }

    if parsed is None:
        # LLM completely failed — return fallback action directly
        fallback_text = (
            "Sorry, I had trouble understanding that. Could you try again in one short sentence?"
        )
        updates["action"] = build_message_action(fallback_text)
        updates["parsed_llm_response"] = None
        updates["conversation_history"] = (
            history_entries
            + [{"role": "assistant", "content": fallback_text}]
        )
    else:
        updates["parsed_llm_response"] = parsed

    return updates

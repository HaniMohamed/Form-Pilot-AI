"""
FormPilot AI graph state definition.

Defines the typed state that flows through all LangGraph nodes.
Replaces the ad-hoc instance variables on the old FormOrchestrator
with a single, inspectable TypedDict.

Uses LangGraph reducers for fields that accumulate across nodes:
- answers: merge semantics (new answers merged into existing)
- conversation_history: append semantics (new entries appended)
"""

from operator import add
from typing import Annotated, Any, TypedDict


def merge_answers(current: dict, update: dict) -> dict:
    """Reducer that merges answer updates into the existing answers dict."""
    merged = dict(current) if current else {}
    if update:
        merged.update(update)
    return merged


class FormPilotState(TypedDict, total=False):
    """Complete state for a form-filling conversation turn.

    Split into sections:
    - Input:        Set by the caller each turn (user message, tool results)
    - Accumulated:  Persists across turns (answers, history, field metadata)
    - Phase:        Tracks where we are in the conversation flow
    - Output:       The action dict returned to the UI after each turn
    - Intermediate: Ephemeral fields used for inter-node communication
    """

    # --- Input (set per request) ---
    form_context_md: str
    user_message: str
    tool_results: list[dict] | None
    llm: Any  # BaseChatModel instance — injected, not serialized

    # --- Accumulated state (persists across turns, with reducers) ---
    answers: Annotated[dict[str, Any], merge_answers]
    conversation_history: Annotated[list[dict[str, str]], add]
    required_fields: list[str]
    field_types: dict[str, str]

    # --- Phase tracking ---
    initial_extraction_done: bool
    pending_field_id: str | None
    pending_action_type: str | None
    pending_text_value: str | None
    pending_text_field_id: str | None
    pending_tool_name: str | None

    # --- Output (set by finalize node, returned to caller) ---
    action: dict[str, Any]

    # --- Intermediate (ephemeral, reset each turn) ---
    # Raw parsed LLM response before finalization
    parsed_llm_response: dict | None
    # Whether the user_message has been added to conversation_history this turn
    user_message_added: bool

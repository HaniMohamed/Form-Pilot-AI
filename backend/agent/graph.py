"""
LangGraph definition for the FormPilot AI conversation flow.

Defines the StateGraph with nodes, conditional edges, and compiles it
into a runnable graph. Models the conversation flow as an explicit,
inspectable state machine.

Flow:
    START -> route_input -> {greeting, tool_handler, validate_input,
                             extraction, conversation}
    greeting     -> END
    tool_handler -> conversation -> finalize -> END
    validate     -> conversation -> finalize -> END
    extraction   -> {conversation, finalize} (conditional)
    conversation -> {finalize, END} (conditional — END if LLM failed)
    finalize     -> END
"""

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.agent.nodes.conversation import conversation_node
from backend.agent.nodes.extraction import extraction_node
from backend.agent.nodes.finalize import finalize_node
from backend.agent.nodes.greeting import greeting_node
from backend.agent.nodes.step_confirmation import step_confirmation_node
from backend.agent.nodes.tool_handler import tool_handler_node
from backend.agent.nodes.validation import validate_input_node
from backend.agent.prompts import extract_field_type_map, extract_required_field_ids
from backend.agent.frontmatter import (
    get_field_prompt_map,
    get_required_fields_by_step,
    parse_frontmatter,
)
from backend.agent.state import FormPilotState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing functions — decide which node to enter next
# ---------------------------------------------------------------------------


def route_input(state: FormPilotState) -> str:
    """Determine which node to enter based on the current input.

    Routing priority:
    1. New session with empty message -> greeting
    2. Tool results present -> tool_handler
    3. Pending field + user answer (no tool results) -> validate_input
    4. First real message, no extraction yet -> extraction
    5. Default -> conversation
    """
    user_message = state.get("user_message", "")
    tool_results = state.get("tool_results")
    conversation_history = state.get("conversation_history", [])
    pending_field_id = state.get("pending_field_id")
    initial_extraction_done = state.get("initial_extraction_done", False)
    awaiting_step_confirmation = state.get("awaiting_step_confirmation", False)

    # New session with empty message — return greeting
    if not conversation_history and not user_message.strip():
        return "greeting"

    # Tool results from frontend — process them first
    if tool_results:
        return "tool_handler"

    # Step checkpoint is active — user must confirm or request edits
    if awaiting_step_confirmation and user_message.strip():
        return "step_confirmation"

    # User answered a pending field — validate the answer
    if pending_field_id and user_message.strip():
        return "validate_input"

    # First real user message — run bulk extraction
    if not initial_extraction_done and not tool_results:
        return "extraction"

    # Default — continue the conversation
    return "conversation"


def route_after_extraction(state: FormPilotState) -> str:
    """Route after extraction: to finalize (direct action) or conversation.

    If extraction received a direct action from the LLM (e.g. TOOL_CALL),
    route to finalize. Otherwise (multi_answer or failure), route to
    conversation to get the next field action.
    """
    if state.get("parsed_llm_response") is not None:
        return "finalize"
    return "conversation"


def route_after_step_confirmation(state: FormPilotState) -> str:
    """Route after step confirmation handling."""
    if state.get("skip_conversation_turn"):
        return END
    return "conversation"


def route_after_conversation(state: FormPilotState) -> str:
    """Route after conversation: to finalize (success) or END (LLM failed).

    If the LLM call succeeded, the parsed response goes to finalize for
    post-processing. If all retries failed, a fallback action is already
    set and we skip finalize.
    """
    if state.get("parsed_llm_response") is not None:
        return "finalize"
    return END


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    """Build the FormPilot AI state graph (uncompiled).

    Returns:
        A StateGraph instance ready to be compiled.
    """
    graph = StateGraph(FormPilotState)

    # Register nodes
    graph.add_node("greeting", greeting_node)
    graph.add_node("tool_handler", tool_handler_node)
    graph.add_node("step_confirmation", step_confirmation_node)
    graph.add_node("validate_input", validate_input_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("conversation", conversation_node)
    graph.add_node("finalize", finalize_node)

    # Entry point: route based on input
    graph.add_conditional_edges(START, route_input, {
        "greeting": "greeting",
        "tool_handler": "tool_handler",
        "step_confirmation": "step_confirmation",
        "validate_input": "validate_input",
        "extraction": "extraction",
        "conversation": "conversation",
    })

    # Greeting returns directly — no further processing needed
    graph.add_edge("greeting", END)

    # Tool handler and validation always feed into conversation
    graph.add_edge("tool_handler", "conversation")
    graph.add_conditional_edges("step_confirmation", route_after_step_confirmation, {
        "conversation": "conversation",
        END: END,
    })
    graph.add_edge("validate_input", "conversation")

    # Extraction routes conditionally: direct action → finalize,
    # multi_answer or failure → conversation
    graph.add_conditional_edges("extraction", route_after_extraction, {
        "finalize": "finalize",
        "conversation": "conversation",
    })

    # Conversation routes conditionally: success → finalize,
    # LLM failure → END (fallback action already set)
    graph.add_conditional_edges("conversation", route_after_conversation, {
        "finalize": "finalize",
        END: END,
    })

    # Finalize is always the last step
    graph.add_edge("finalize", END)

    return graph


def compile_graph(checkpointer: Any | None = None):
    """Build and compile the FormPilot AI graph.

    Returns:
        A compiled graph ready for invocation via ainvoke().
    """
    graph = build_graph()
    if checkpointer is not None:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()


# ---------------------------------------------------------------------------
# State initialization helper
# ---------------------------------------------------------------------------


def create_initial_state(
    form_context_md: str,
    llm: Any,
) -> FormPilotState:
    """Create the initial state for a new form-filling session.

    Extracts required fields and field types from the markdown form
    definition and sets all tracking fields to their initial values.

    Args:
        form_context_md: The markdown content describing the form.
        llm: A LangChain BaseChatModel instance.

    Returns:
        A fully initialized FormPilotState dict.
    """
    frontmatter, _ = parse_frontmatter(form_context_md)
    required_by_step = get_required_fields_by_step(frontmatter) if frontmatter else {}
    if required_by_step:
        max_step = max(required_by_step.keys())
    else:
        max_step = 1

    return FormPilotState(
        form_context_md=form_context_md,
        llm=llm,
        user_message="",
        tool_results=None,
        answers={},
        conversation_history=[],
        required_fields=extract_required_field_ids(form_context_md),
        required_fields_by_step=required_by_step,
        field_prompt_map=get_field_prompt_map(frontmatter) if frontmatter else {},
        field_types=extract_field_type_map(form_context_md),
        initial_extraction_done=False,
        current_step=1,
        max_step=max_step,
        completed_steps=[],
        awaiting_step_confirmation=False,
        allow_answered_field_update=False,
        pending_field_id=None,
        pending_action_type=None,
        pending_text_value=None,
        pending_text_field_id=None,
        pending_tool_name=None,
        action={},
        parsed_llm_response=None,
        user_message_added=False,
        skip_conversation_turn=False,
    )


def prepare_turn_input(
    state: FormPilotState,
    user_message: str,
    tool_results: list[dict] | None = None,
) -> FormPilotState:
    """Prepare state for a new conversation turn.

    Updates the input fields and resets ephemeral per-turn fields
    while preserving accumulated state (answers, history, etc.).

    Args:
        state: The current session state.
        user_message: The new user message.
        tool_results: Optional tool results from the frontend.

    Returns:
        Updated state ready for graph invocation.
    """
    updated = dict(state)
    updated["user_message"] = user_message
    updated["tool_results"] = tool_results
    updated["action"] = {}
    updated["parsed_llm_response"] = None
    updated["user_message_added"] = False
    updated["skip_conversation_turn"] = False
    updated["allow_answered_field_update"] = False
    return FormPilotState(**updated)

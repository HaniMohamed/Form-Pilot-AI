"""
Tool handler node — processes tool results returned from the frontend.

Adds tool result data and directives to conversation history so the
LLM can use the results to present options or continue the form.
"""

import json
import logging

from backend.agent.state import FormPilotState
from backend.agent.utils import extract_options_hint

logger = logging.getLogger(__name__)


def tool_handler_node(state: FormPilotState) -> dict:
    """Process tool results into conversation history.

    For each tool result, extracts option hints and adds a directive
    to help the LLM use the data effectively.

    Returns:
        Partial state with conversation_history updates and cleared tool state.
    """
    tool_results = state.get("tool_results") or []
    user_message = state.get("user_message", "")
    history_entries: list[dict[str, str]] = []

    for result in tool_results:
        tool_name = result.get("tool_name", "unknown")
        tool_data = result.get("result", {})

        # Extract option names from the result to help the LLM
        options_hint = extract_options_hint(tool_data)

        # Build directive with tool result data
        directive = f"[Tool result for {tool_name}]: {json.dumps(tool_data)}"
        if options_hint:
            directive += (
                f"\n\n[INSTRUCTION: Use the data above. "
                f"Return ASK_DROPDOWN with these options: {options_hint}]"
            )
        else:
            directive += (
                "\n\n[INSTRUCTION: Use the data above to continue the form. "
                "Return the appropriate JSON action.]"
            )
        history_entries.append({"role": "user", "content": directive})

    # Add user message to history if non-empty
    if user_message.strip():
        history_entries.append({"role": "user", "content": user_message})

    return {
        "conversation_history": history_entries,
        "pending_tool_name": None,
        "user_message_added": True,
    }

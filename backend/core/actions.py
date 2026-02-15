"""
AI Action Protocol — structured output models.

Defines the action types the AI returns to the Flutter web app.
Each action maps to a specific UI widget or behavior. The web app
reads the action JSON and renders the appropriate component.

Now fully LLM-driven: the LLM chooses which action to emit based on
the markdown form context. No deterministic field-type mapping needed.
"""

from typing import Any


# --- Action Builders ---


def build_message_action(text: str) -> dict:
    """Build a MESSAGE action for conversational responses.

    Args:
        text: The message text to display.

    Returns:
        A dict representing the MESSAGE action JSON.
    """
    return {
        "action": "MESSAGE",
        "text": text,
    }


def build_completion_payload(answers: dict[str, Any]) -> dict:
    """Build the FORM_COMPLETE action payload.

    Args:
        answers: All collected answers.

    Returns:
        A dict representing the FORM_COMPLETE action JSON.
    """
    return {
        "action": "FORM_COMPLETE",
        "data": dict(answers),
    }


def build_tool_call_action(
    tool_name: str, tool_args: dict | None = None, message: str = ""
) -> dict:
    """Build a TOOL_CALL action requesting the frontend to execute a tool.

    Args:
        tool_name: Name of the tool to call (e.g. 'get_establishments').
        tool_args: Arguments to pass to the tool.
        message: Optional message to display while the tool executes.

    Returns:
        A dict representing the TOOL_CALL action JSON.
    """
    return {
        "action": "TOOL_CALL",
        "tool_name": tool_name,
        "tool_args": tool_args or {},
        "message": message,
    }

"""
Greeting node — builds the initial welcome message.

Extracts the form title and required field labels from the markdown
to build a warm, informative greeting that helps the user understand
what data is needed upfront.
"""

from backend.agent.prompts import extract_form_title, summarize_required_fields
from backend.agent.state import FormPilotState
from backend.core.actions import build_message_action


def greeting_node(state: FormPilotState) -> dict:
    """Build the initial greeting and return it as a MESSAGE action.

    Returns:
        Partial state with action and conversation_history update.
    """
    form_context_md = state["form_context_md"]
    form_title = extract_form_title(form_context_md)
    summary = summarize_required_fields(form_context_md)

    if summary:
        greeting = (
            f"Hi there! I'm FormPilot AI, and I'll be helping you fill out "
            f"the **{form_title}** form.\n\n"
            f"{summary}.\n\n"
            f"Feel free to tell me everything you know in one message — "
            f"I'll extract what I can and only ask about the rest!"
        )
    else:
        greeting = (
            f"Hi there! I'm FormPilot AI, and I'll be helping you fill out "
            f"the **{form_title}** form.\n\n"
            f"Go ahead and describe all the information you have — "
            f"I'll take care of filling in the form and only ask about "
            f"anything that's missing!"
        )

    return {
        "action": build_message_action(greeting),
        "conversation_history": [{"role": "assistant", "content": greeting}],
    }

"""
Compatibility wrapper around the LangGraph-based conversation engine.

Preserves the FormOrchestrator interface used by existing tests while
delegating all logic to the compiled LangGraph state machine. The
production code path (routes.py) uses the graph directly and does not
go through this wrapper.

Also re-exports validation functions from utils.py for any code that
imported them from this module.
"""

from typing import Any

from backend.agent.graph import compile_graph, create_initial_state, prepare_turn_input
from backend.agent.utils import (  # noqa: F401 — re-export for backward compat
    validate_answer_for_action,
    validate_date_answer,
    validate_datetime_answer,
    validate_time_answer,
)

# Compile the graph once at module level (shared across all wrapper instances)
_compiled_graph = compile_graph()


class FormOrchestrator:
    """Compatibility wrapper that delegates to the LangGraph state machine.

    Provides the same interface as the original orchestrator so existing
    tests and integrations continue to work unchanged.

    Args:
        form_context_md: The markdown content describing the form.
        llm: A LangChain BaseChatModel instance.
    """

    def __init__(self, form_context_md: str, llm: Any):
        self._state = create_initial_state(form_context_md, llm)
        self._graph = _compiled_graph

    def get_initial_action(self) -> dict:
        """Get the first action — a friendly greeting.

        Invokes the graph with an empty user message, which routes
        to the greeting node.

        Returns:
            A MESSAGE action dict with the greeting.
        """
        turn_state = prepare_turn_input(self._state, user_message="")
        result = _run_sync(self._graph.ainvoke(turn_state))
        self._state = result
        return result.get("action", {})

    async def process_user_message(
        self,
        user_message: str,
        tool_results: list[dict] | None = None,
    ) -> dict:
        """Process a user message or tool results and return the next action.

        Args:
            user_message: The raw text message from the user.
            tool_results: Results from TOOL_CALL actions executed by the frontend.

        Returns:
            An action dict for the UI to render.
        """
        turn_state = prepare_turn_input(
            self._state,
            user_message=user_message,
            tool_results=tool_results,
        )
        result = await self._graph.ainvoke(turn_state)
        self._state = result
        return result.get("action", {})

    def get_answers(self) -> dict[str, Any]:
        """Return the current collected answers."""
        return dict(self._state.get("answers", {}))

    @property
    def answers(self) -> dict[str, Any]:
        """Direct access to the answers dict (for test assertions)."""
        return dict(self._state.get("answers", {}))

    @property
    def conversation_history(self) -> list[dict[str, str]]:
        """Direct access to conversation history (for test assertions)."""
        return list(self._state.get("conversation_history", []))

    @property
    def _initial_extraction_done(self) -> bool:
        """Direct access to extraction flag (for test assertions)."""
        return self._state.get("initial_extraction_done", False)

    @property
    def _pending_field_id(self) -> str | None:
        """Direct access to pending field (for test assertions)."""
        return self._state.get("pending_field_id")

    @property
    def _pending_tool_name(self) -> str | None:
        """Direct access to pending tool (for test assertions)."""
        return self._state.get("pending_tool_name")

    @property
    def form_context_md(self) -> str:
        """Direct access to form context (for test assertions)."""
        return self._state.get("form_context_md", "")


def _run_sync(coro):
    """Run an async coroutine synchronously.

    Used by get_initial_action() which is a sync method in the original API.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an existing event loop — create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)

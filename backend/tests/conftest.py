"""
Shared test fixtures and helpers for the FormPilot AI test suite.

Provides GraphRunner — a lightweight wrapper around the compiled
LangGraph that gives tests a simple sync/async interface without
depending on any legacy orchestrator code.
"""

import asyncio
from typing import Any

from backend.agent.graph import compile_graph, create_initial_state, prepare_turn_input

# Compile once — shared across all tests in the session
_compiled_graph = compile_graph()


class GraphRunner:
    """Test helper that wraps the LangGraph with a simple interface.

    Usage:
        runner = GraphRunner(form_md, mock_llm)
        action = runner.get_initial_action()
        action = await runner.process_user_message("hello")
        answers = runner.answers
    """

    def __init__(self, form_context_md: str, llm: Any):
        self._state = create_initial_state(form_context_md, llm)

    def get_initial_action(self) -> dict:
        """Get the greeting action (sync — runs the graph in a new event loop)."""
        turn = prepare_turn_input(self._state, user_message="")
        self._state = _run_sync(_compiled_graph.ainvoke(turn))
        return self._state.get("action", {})

    async def process_user_message(
        self,
        user_message: str,
        tool_results: list[dict] | None = None,
    ) -> dict:
        """Process a user message and return the next action."""
        turn = prepare_turn_input(self._state, user_message, tool_results)
        self._state = await _compiled_graph.ainvoke(turn)
        return self._state.get("action", {})

    def get_answers(self) -> dict[str, Any]:
        """Return current collected answers."""
        return dict(self._state.get("answers", {}))

    @property
    def answers(self) -> dict[str, Any]:
        return dict(self._state.get("answers", {}))

    @property
    def conversation_history(self) -> list[dict[str, str]]:
        return list(self._state.get("conversation_history", []))

    @property
    def _initial_extraction_done(self) -> bool:
        return self._state.get("initial_extraction_done", False)


def _run_sync(coro):
    """Run an async coroutine synchronously (for get_initial_action)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)

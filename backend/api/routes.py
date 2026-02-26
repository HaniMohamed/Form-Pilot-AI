"""
FastAPI routes for the FormPilot AI backend.

Endpoints:
- POST /chat              — process a user message in a conversation
- GET  /schemas           — list available example schemas (.md files)
- GET  /schemas/{filename} — get a specific schema file content
- POST /sessions/reset    — reset/delete a conversation session
- GET  /health            — health check
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agent.graph import prepare_turn_input

logger = logging.getLogger(__name__)

router = APIRouter()

# These will be injected by the app factory
_session_store = None
_llm = None
_graph = None

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


def configure_routes(session_store, llm, graph=None):
    """Inject the session store, LLM, and compiled graph into the routes module.

    Called by the app factory during startup.
    """
    global _session_store, _llm, _graph
    _session_store = session_store
    _llm = llm
    _graph = graph


# --- Request / Response Models ---


class ChatRequest(BaseModel):
    """Request body for the /chat endpoint."""

    form_context_md: str
    user_message: str
    conversation_id: str | None = None
    tool_results: list[dict[str, Any]] | None = None


class ChatResponse(BaseModel):
    """Response body for the /chat endpoint."""

    action: dict[str, Any]
    conversation_id: str
    answers: dict[str, Any]


class ResetRequest(BaseModel):
    """Request body for the /sessions/reset endpoint."""

    conversation_id: str


# --- Endpoints ---


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process a user message in a form-filling conversation.

    If conversation_id is provided, resumes an existing session.
    Otherwise, creates a new session from the provided markdown context.
    The LangGraph state machine handles all routing: greeting, extraction,
    validation, tool handling, and conversation.
    """
    if _session_store is None or _llm is None or _graph is None:
        raise HTTPException(status_code=500, detail="Server not properly configured")

    if not request.form_context_md.strip():
        raise HTTPException(status_code=400, detail="form_context_md cannot be empty")

    # Try to resume existing session
    session = None
    conversation_id = request.conversation_id

    if conversation_id:
        try:
            # Durable stores may need llm to rehydrate runtime state.
            session = _session_store.get_session(conversation_id, llm=_llm)
        except TypeError:
            session = _session_store.get_session(conversation_id)

    # Create new session if needed
    if session is None:
        conversation_id, session = _session_store.create_session(
            form_context_md=request.form_context_md,
            llm=_llm,
            conversation_id=conversation_id,
        )

    # Prepare state for this turn (set input, reset ephemeral fields)
    turn_state = prepare_turn_input(
        state=session.state,
        user_message=request.user_message,
        tool_results=request.tool_results,
    )

    # Invoke the LangGraph state machine
    try:
        run_config = {"configurable": {"thread_id": conversation_id}}
        result_state = await _graph.ainvoke(turn_state, config=run_config)
    except Exception as e:
        logger.error("Error processing message: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}",
        )

    # Persist the updated state back to the store
    if hasattr(_session_store, "save_session"):
        _session_store.save_session(conversation_id, result_state)
    else:
        # Backward compatibility with simple in-memory store.
        session.state = result_state

    return ChatResponse(
        action=result_state.get("action", {}),
        conversation_id=conversation_id,
        answers=result_state.get("answers", {}),
    )


@router.get("/schemas")
async def list_schemas():
    """List available example schema files (.md)."""
    schemas = []
    if SCHEMAS_DIR.exists():
        for path in sorted(SCHEMAS_DIR.glob("*.md")):
            try:
                content = path.read_text(encoding="utf-8")
                # Extract title from first markdown heading
                title = path.stem
                for line in content.splitlines():
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break
                schemas.append({
                    "filename": path.name,
                    "title": title,
                    "size": len(content),
                })
            except OSError:
                continue
    return {"schemas": schemas}


@router.get("/schemas/{filename}")
async def get_schema(filename: str):
    """Get a specific schema file content by filename."""
    path = SCHEMAS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Schema '{filename}' not found")

    try:
        content = path.read_text(encoding="utf-8")
        return {"filename": filename, "content": content}
    except OSError:
        raise HTTPException(status_code=500, detail=f"Error reading schema file '{filename}'")


@router.post("/sessions/reset")
async def reset_session(request: ResetRequest):
    """Delete a conversation session and start fresh."""
    if _session_store is None:
        raise HTTPException(status_code=500, detail="Server not properly configured")

    deleted = _session_store.delete_session(request.conversation_id)
    return {
        "success": deleted,
        "message": "Session reset" if deleted else "Session not found",
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    session_count = _session_store.count() if _session_store else 0
    return {
        "status": "healthy",
        "active_sessions": session_count,
    }

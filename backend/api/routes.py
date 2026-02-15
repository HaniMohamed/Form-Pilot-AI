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

logger = logging.getLogger(__name__)

router = APIRouter()

# These will be injected by the app factory
_session_store = None
_llm = None

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


def configure_routes(session_store, llm):
    """Inject the session store and LLM into the routes module.

    Called by the app factory during startup.
    """
    global _session_store, _llm
    _session_store = session_store
    _llm = llm


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
    """
    if _session_store is None or _llm is None:
        raise HTTPException(status_code=500, detail="Server not properly configured")

    if not request.form_context_md.strip():
        raise HTTPException(status_code=400, detail="form_context_md cannot be empty")

    # Try to resume existing session
    session = None
    conversation_id = request.conversation_id

    if conversation_id:
        session = _session_store.get_session(conversation_id)

    # Create new session if needed
    if session is None:
        conversation_id, session = _session_store.create_session(
            form_context_md=request.form_context_md,
            llm=_llm,
            conversation_id=conversation_id,
        )

        # If this is the first message and it's empty/greeting, return initial action
        if not request.user_message.strip() and not request.tool_results:
            action = session.orchestrator.get_initial_action()
            return ChatResponse(
                action=action,
                conversation_id=conversation_id,
                answers=session.orchestrator.get_answers(),
            )

    # Process the user message (with optional tool results)
    try:
        action = await session.orchestrator.process_user_message(
            user_message=request.user_message,
            tool_results=request.tool_results,
        )
    except Exception as e:
        logger.error("Error processing message: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}",
        )

    return ChatResponse(
        action=action,
        conversation_id=conversation_id,
        answers=session.orchestrator.get_answers(),
    )


@router.get("/schemas")
async def list_schemas():
    """List available example schema files (.md and .json)."""
    schemas = []
    if SCHEMAS_DIR.exists():
        for path in sorted(SCHEMAS_DIR.glob("*.md")):
            try:
                content = path.read_text()
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
        content = path.read_text()
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

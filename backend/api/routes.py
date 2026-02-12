"""
FastAPI routes for the FormPilot AI backend.

Endpoints:
- POST /chat              — process a user message in a conversation
- POST /validate-schema   — validate a form schema JSON
- GET  /schemas           — list available example schemas
- POST /sessions/reset    — reset/delete a conversation session
- GET  /health            — health check
"""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from backend.core.schema import FormSchema

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

    form_schema: dict[str, Any]
    user_message: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    """Response body for the /chat endpoint."""

    action: dict[str, Any]
    conversation_id: str
    answers: dict[str, Any]


class ValidateSchemaRequest(BaseModel):
    """Request body for the /validate-schema endpoint."""

    form_schema: dict[str, Any]


class ValidateSchemaResponse(BaseModel):
    """Response body for the /validate-schema endpoint."""

    valid: bool
    errors: list[str]


class ResetRequest(BaseModel):
    """Request body for the /sessions/reset endpoint."""

    conversation_id: str


# --- Endpoints ---


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process a user message in a form-filling conversation.

    If conversation_id is provided, resumes an existing session.
    Otherwise, creates a new session from the provided schema.
    """
    if _session_store is None or _llm is None:
        raise HTTPException(status_code=500, detail="Server not properly configured")

    # Try to resume existing session
    session = None
    conversation_id = request.conversation_id

    if conversation_id:
        session = _session_store.get_session(conversation_id)

    # Create new session if needed
    if session is None:
        try:
            schema = FormSchema(**request.form_schema)
        except ValidationError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid form schema: {_format_validation_errors(e)}",
            )

        conversation_id, session = _session_store.create_session(
            schema=schema,
            llm=_llm,
            conversation_id=conversation_id,
        )

        # If this is the first message and it's empty/greeting, return initial action
        if not request.user_message.strip():
            action = session.orchestrator.get_initial_action()
            return ChatResponse(
                action=action,
                conversation_id=conversation_id,
                answers=session.state_manager.get_visible_answers(),
            )

    # Process the user message
    try:
        action = await session.orchestrator.process_user_message(request.user_message)
    except Exception as e:
        logger.error("Error processing message: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}",
        )

    return ChatResponse(
        action=action,
        conversation_id=conversation_id,
        answers=session.state_manager.get_visible_answers(),
    )


@router.post("/validate-schema", response_model=ValidateSchemaResponse)
async def validate_schema(request: ValidateSchemaRequest):
    """Validate a form schema JSON structure.

    Returns whether the schema is valid and any validation errors.
    """
    try:
        FormSchema(**request.form_schema)
        return ValidateSchemaResponse(valid=True, errors=[])
    except ValidationError as e:
        errors = _format_validation_errors(e)
        return ValidateSchemaResponse(valid=False, errors=errors)


@router.get("/schemas")
async def list_schemas():
    """List available example schema files."""
    schemas = []
    if SCHEMAS_DIR.exists():
        for path in sorted(SCHEMAS_DIR.glob("*.json")):
            try:
                with open(path) as f:
                    data = json.load(f)
                schemas.append({
                    "filename": path.name,
                    "form_id": data.get("form_id", path.stem),
                    "field_count": len(data.get("fields", [])),
                })
            except (json.JSONDecodeError, OSError):
                continue
    return {"schemas": schemas}


@router.get("/schemas/{filename}")
async def get_schema(filename: str):
    """Get a specific example schema by filename."""
    path = SCHEMAS_DIR / filename
    if not path.exists() or not path.suffix == ".json":
        raise HTTPException(status_code=404, detail=f"Schema '{filename}' not found")

    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Invalid JSON in schema file '{filename}'")


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


# --- Helpers ---


def _format_validation_errors(e: ValidationError) -> list[str]:
    """Format Pydantic validation errors into readable strings."""
    errors = []
    for err in e.errors():
        loc = " → ".join(str(x) for x in err.get("loc", []))
        msg = err.get("msg", "Unknown error")
        errors.append(f"{loc}: {msg}" if loc else msg)
    return errors

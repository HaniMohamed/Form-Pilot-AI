"""
In-memory session store for conversation state.

Each conversation session holds a FormStateManager and a FormOrchestrator.
Sessions are created automatically on the first /chat call and can be
cleaned up after a timeout.
"""

import time
import uuid
from typing import Any

from backend.agent.orchestrator import FormOrchestrator
from backend.core.form_state import FormStateManager
from backend.core.schema import FormSchema


# Default session timeout: 30 minutes
DEFAULT_SESSION_TIMEOUT_SECONDS = 30 * 60


class Session:
    """A single conversation session."""

    def __init__(self, schema: FormSchema, orchestrator: FormOrchestrator):
        self.schema = schema
        self.orchestrator = orchestrator
        self.state_manager = orchestrator.state
        self.created_at: float = time.time()
        self.last_accessed_at: float = time.time()

    def touch(self) -> None:
        """Update the last accessed timestamp."""
        self.last_accessed_at = time.time()

    def is_expired(self, timeout_seconds: int = DEFAULT_SESSION_TIMEOUT_SECONDS) -> bool:
        """Check if the session has expired."""
        return (time.time() - self.last_accessed_at) > timeout_seconds


class SessionStore:
    """In-memory store for conversation sessions.

    Thread-safe for basic use. For production, consider a proper
    session backend (Redis, etc).
    """

    def __init__(self, timeout_seconds: int = DEFAULT_SESSION_TIMEOUT_SECONDS):
        self._sessions: dict[str, Session] = {}
        self._timeout_seconds = timeout_seconds

    def create_session(
        self,
        schema: FormSchema,
        llm: Any,
        conversation_id: str | None = None,
    ) -> tuple[str, Session]:
        """Create a new session for a form schema.

        Args:
            schema: A validated FormSchema.
            llm: A LangChain BaseChatModel instance.
            conversation_id: Optional custom ID. Auto-generated if not provided.

        Returns:
            Tuple of (conversation_id, Session).
        """
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())

        state_manager = FormStateManager(schema)
        orchestrator = FormOrchestrator(state_manager, llm)
        session = Session(schema, orchestrator)

        self._sessions[conversation_id] = session
        return conversation_id, session

    def get_session(self, conversation_id: str) -> Session | None:
        """Retrieve a session by conversation ID.

        Returns None if the session doesn't exist or has expired.
        Automatically cleans up expired sessions.
        """
        session = self._sessions.get(conversation_id)
        if session is None:
            return None

        if session.is_expired(self._timeout_seconds):
            del self._sessions[conversation_id]
            return None

        session.touch()
        return session

    def delete_session(self, conversation_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        if conversation_id in self._sessions:
            del self._sessions[conversation_id]
            return True
        return False

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns the count of removed sessions."""
        expired = [
            cid for cid, session in self._sessions.items()
            if session.is_expired(self._timeout_seconds)
        ]
        for cid in expired:
            del self._sessions[cid]
        return len(expired)

    def count(self) -> int:
        """Return the number of active sessions."""
        return len(self._sessions)

    def list_session_ids(self) -> list[str]:
        """Return all active session IDs."""
        return list(self._sessions.keys())

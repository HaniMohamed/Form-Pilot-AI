"""
Session stores for conversation state.

Each session holds a FormPilotState dict that tracks all conversation
progress. Sessions are created on the first /chat call and cleaned up
after a timeout.
"""

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from backend.agent.graph import create_initial_state
from backend.agent.state import FormPilotState


# Default session timeout: 30 minutes
DEFAULT_SESSION_TIMEOUT_SECONDS = 30 * 60


class Session:
    """A single conversation session.

    Holds the LangGraph state dict that persists across conversation turns.
    """

    def __init__(self, state: FormPilotState):
        self.state: FormPilotState = state
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
        self._lock = threading.RLock()

    def create_session(
        self,
        form_context_md: str,
        llm: Any,
        conversation_id: str | None = None,
    ) -> tuple[str, Session]:
        """Create a new session for a markdown form context.

        Initializes the LangGraph state with the form definition
        and LLM instance.

        Args:
            form_context_md: The markdown content describing the form.
            llm: A LangChain BaseChatModel instance.
            conversation_id: Optional custom ID. Auto-generated if not provided.

        Returns:
            Tuple of (conversation_id, Session).
        """
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())

        state = create_initial_state(form_context_md, llm)
        session = Session(state)

        with self._lock:
            self._sessions[conversation_id] = session
        return conversation_id, session

    def get_session(self, conversation_id: str) -> Session | None:
        """Retrieve a session by conversation ID.

        Returns None if the session doesn't exist or has expired.
        Automatically cleans up expired sessions.
        """
        with self._lock:
            session = self._sessions.get(conversation_id)
        if session is None:
            return None

        if session.is_expired(self._timeout_seconds):
            with self._lock:
                if conversation_id in self._sessions:
                    del self._sessions[conversation_id]
            return None

        session.touch()
        return session

    def save_session(self, conversation_id: str, state: FormPilotState) -> bool:
        """Persist updated state for an existing session."""
        with self._lock:
            session = self._sessions.get(conversation_id)
            if session is None:
                return False
            session.state = state
            session.touch()
            return True

    def delete_session(self, conversation_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        with self._lock:
            if conversation_id in self._sessions:
                del self._sessions[conversation_id]
                return True
            return False

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns the count of removed sessions."""
        with self._lock:
            expired = [
                cid for cid, session in self._sessions.items()
                if session.is_expired(self._timeout_seconds)
            ]
            for cid in expired:
                del self._sessions[cid]
        return len(expired)

    def count(self) -> int:
        """Return the number of active sessions."""
        with self._lock:
            return len(self._sessions)

    def list_session_ids(self) -> list[str]:
        """Return all active session IDs."""
        with self._lock:
            return list(self._sessions.keys())


def _serialize_state(state: FormPilotState) -> str:
    """Serialize a session state to JSON (excluding non-serializable LLM)."""
    serializable = dict(state)
    # LLM object is runtime dependency and cannot be JSON-serialized.
    serializable.pop("llm", None)
    return json.dumps(serializable, ensure_ascii=False)


def _deserialize_state(state_json: str, llm: Any) -> FormPilotState:
    """Deserialize JSON state and inject runtime LLM dependency."""
    raw = json.loads(state_json)
    raw["llm"] = llm
    return FormPilotState(**raw)


class SQLiteSessionStore:
    """SQLite-backed durable session store.

    Useful when you need session state to survive backend restarts without
    introducing external infrastructure.
    """

    def __init__(
        self,
        db_path: str,
        timeout_seconds: int = DEFAULT_SESSION_TIMEOUT_SECONDS,
    ):
        self._db_path = db_path
        self._timeout_seconds = timeout_seconds
        self._lock = threading.RLock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    conversation_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_accessed_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def create_session(
        self,
        form_context_md: str,
        llm: Any,
        conversation_id: str | None = None,
    ) -> tuple[str, Session]:
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())
        now = time.time()
        state = create_initial_state(form_context_md, llm)
        state_json = _serialize_state(state)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions
                (conversation_id, state_json, created_at, last_accessed_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, state_json, now, now),
            )
            conn.commit()
        return conversation_id, Session(state)

    def get_session(self, conversation_id: str, llm: Any | None = None) -> Session | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT state_json, last_accessed_at FROM sessions WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return None

            last_accessed = float(row["last_accessed_at"])
            if (time.time() - last_accessed) > self._timeout_seconds:
                conn.execute("DELETE FROM sessions WHERE conversation_id = ?", (conversation_id,))
                conn.commit()
                return None

            conn.execute(
                "UPDATE sessions SET last_accessed_at = ? WHERE conversation_id = ?",
                (time.time(), conversation_id),
            )
            conn.commit()

        if llm is None:
            raise ValueError("llm is required when loading sessions from SQLiteSessionStore")
        state = _deserialize_state(str(row["state_json"]), llm)
        return Session(state)

    def save_session(self, conversation_id: str, state: FormPilotState) -> bool:
        state_json = _serialize_state(state)
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE sessions
                SET state_json = ?, last_accessed_at = ?
                WHERE conversation_id = ?
                """,
                (state_json, time.time(), conversation_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_session(self, conversation_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE conversation_id = ?",
                (conversation_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def cleanup_expired(self) -> int:
        cutoff = time.time() - self._timeout_seconds
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE last_accessed_at < ?",
                (cutoff,),
            )
            conn.commit()
            return cursor.rowcount

    def count(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()
            return int(row["c"]) if row else 0

    def list_session_ids(self) -> list[str]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT conversation_id FROM sessions").fetchall()
            return [str(r["conversation_id"]) for r in rows]

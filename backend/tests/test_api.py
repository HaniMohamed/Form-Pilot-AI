"""
Integration tests for the FastAPI API layer.

Tests cover:
- POST /api/chat with markdown form context
- Session persistence across multiple /chat calls
- Tool results pass-through
- Error responses for malformed requests
- GET /api/schemas listing (.md files)
- GET /api/schemas/{filename}
- POST /api/sessions/reset
- GET /api/health
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import configure_routes, router
from backend.core.session import SessionStore

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"

# Sample markdown form context for testing
SAMPLE_MD = """
# Leave Request Form

## Fields
- **leave_type** (dropdown, required): Type of leave?
  Options: Annual, Sick, Emergency
- **start_date** (date, required): Start date?
- **end_date** (date, required): End date?
- **reason** (text, required): Reason for leave?
"""


# --- Mock LLM for integration tests ---


class MockLLM:
    """Mock LLM that returns pre-configured JSON responses."""

    def __init__(self, responses: list[dict] | None = None):
        self.responses = list(responses or [])
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        if not self.responses:
            # Default: return extraction with one field
            response_dict = {
                "intent": "multi_answer",
                "answers": {"leave_type": "Annual"},
                "message": "Got it!",
            }
        else:
            response_dict = self.responses.pop(0)
        result = MagicMock()
        result.content = json.dumps(response_dict)
        return result


# --- Fixtures ---


def _create_test_app(llm=None):
    """Create a FastAPI test client with a mock LLM."""
    app = FastAPI()
    session_store = SessionStore(timeout_seconds=3600)
    mock_llm = llm or MockLLM()
    configure_routes(session_store, mock_llm)
    app.include_router(router, prefix="/api")
    return TestClient(app), session_store, mock_llm


# --- /api/chat tests ---


class TestChat:
    """Tests for the POST /api/chat endpoint."""

    def test_first_message_creates_session(self):
        """First chat message should create a new session and return an action."""
        mock_llm = MockLLM([
            # Extraction response
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual"},
             "message": "Got it!"},
            # Conversation response
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start date?",
             "message": "I captured Annual leave. When does it start?"},
        ])
        client, store, _ = _create_test_app(mock_llm)

        response = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "I want annual leave",
        })

        assert response.status_code == 200
        data = response.json()
        assert "conversation_id" in data
        assert "action" in data
        assert "answers" in data
        assert store.count() == 1

    def test_empty_first_message_returns_initial_action(self):
        """Empty first message should return the greeting MESSAGE action."""
        client, store, _ = _create_test_app()

        response = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "",
        })

        assert response.status_code == 200
        data = response.json()
        assert "conversation_id" in data
        action = data["action"]
        assert action["action"] == "MESSAGE"
        assert "text" in action

    def test_session_persistence(self):
        """Multiple messages with the same conversation_id should use the same session."""
        mock_llm = MockLLM([
            # Extraction: captures leave_type
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual"},
             "message": "Annual leave captured."},
            # Conversation: ask start_date
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start date?",
             "message": "When does it start?"},
            # Follow-up: answer start_date
            {"action": "ASK_DATE", "field_id": "end_date",
             "label": "End date?",
             "message": "And when does it end?"},
        ])
        client, store, _ = _create_test_app(mock_llm)

        # First message — triggers extraction
        r1 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "I want annual leave",
        })
        cid = r1.json()["conversation_id"]
        assert store.count() == 1

        # Second message with same conversation_id
        r2 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "Starting March 1st",
            "conversation_id": cid,
        })
        assert r2.status_code == 200
        assert store.count() == 1

    def test_empty_markdown_returns_400(self):
        """Chat with empty markdown should return 400."""
        client, _, _ = _create_test_app()

        response = client.post("/api/chat", json={
            "form_context_md": "",
            "user_message": "Hello",
        })

        assert response.status_code == 400

    def test_chat_missing_body_fields(self):
        """Chat with missing required fields should return 422."""
        client, _, _ = _create_test_app()

        response = client.post("/api/chat", json={})
        assert response.status_code == 422

    def test_custom_conversation_id(self):
        """Client can provide a custom conversation_id."""
        mock_llm = MockLLM([
            {"intent": "multi_answer", "answers": {"leave_type": "Sick"},
             "message": "Ok."},
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start date?", "message": "When?"},
        ])
        client, store, _ = _create_test_app(mock_llm)
        custom_id = "my-custom-session-123"

        response = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "Sick leave",
            "conversation_id": custom_id,
        })

        assert response.status_code == 200
        assert response.json()["conversation_id"] == custom_id
        assert store.get_session(custom_id) is not None

    def test_tool_results_accepted(self):
        """Chat endpoint accepts tool_results in the request."""
        mock_llm = MockLLM([
            # After tool results, LLM continues
            {"action": "ASK_DROPDOWN", "field_id": "establishment",
             "label": "Select establishment",
             "options": ["Company A", "Company B"],
             "message": "Please select."},
        ])
        client, store, _ = _create_test_app(mock_llm)

        # First create a session
        r0 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "",
        })
        cid = r0.json()["conversation_id"]

        # Send tool results
        response = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "",
            "conversation_id": cid,
            "tool_results": [{
                "tool_name": "get_establishments",
                "result": {"establishments": ["Company A", "Company B"]},
            }],
        })
        assert response.status_code == 200


# --- /api/schemas tests ---


class TestSchemas:
    """Tests for the GET /api/schemas endpoint."""

    def test_list_schemas(self):
        client, _, _ = _create_test_app()
        response = client.get("/api/schemas")
        assert response.status_code == 200
        data = response.json()
        assert "schemas" in data
        # Should find the .md file(s)
        assert len(data["schemas"]) >= 1

    def test_get_specific_schema(self):
        """Get a specific .md schema file."""
        client, _, _ = _create_test_app()
        # Get the first available schema
        list_response = client.get("/api/schemas")
        schemas = list_response.json()["schemas"]
        if schemas:
            filename = schemas[0]["filename"]
            response = client.get(f"/api/schemas/{filename}")
            assert response.status_code == 200
            data = response.json()
            assert "content" in data
            assert "filename" in data

    def test_get_nonexistent_schema(self):
        client, _, _ = _create_test_app()
        response = client.get("/api/schemas/nonexistent.md")
        assert response.status_code == 404


# --- /api/sessions/reset tests ---


class TestSessionReset:
    """Tests for the POST /api/sessions/reset endpoint."""

    def test_reset_existing_session(self):
        client, store, _ = _create_test_app()

        # Create a session
        r = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "",
        })
        cid = r.json()["conversation_id"]
        assert store.count() == 1

        # Reset it
        r2 = client.post("/api/sessions/reset", json={"conversation_id": cid})
        assert r2.status_code == 200
        assert r2.json()["success"] is True
        assert store.count() == 0

    def test_reset_nonexistent_session(self):
        client, _, _ = _create_test_app()
        r = client.post("/api/sessions/reset", json={"conversation_id": "does-not-exist"})
        assert r.status_code == 200
        assert r.json()["success"] is False


# --- /api/health tests ---


class TestHealth:
    """Tests for the GET /api/health endpoint."""

    def test_health_check(self):
        client, _, _ = _create_test_app()
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["active_sessions"] == 0


# --- Session store tests ---


class TestSessionStore:
    """Tests for the SessionStore directly."""

    def test_session_expiry(self):
        """Expired sessions should not be returned."""
        from backend.core.session import SessionStore

        store = SessionStore(timeout_seconds=0)
        cid, session = store.create_session(SAMPLE_MD, MockLLM())

        import time
        time.sleep(0.01)
        assert store.get_session(cid) is None

    def test_cleanup_expired(self):
        from backend.core.session import SessionStore

        store = SessionStore(timeout_seconds=0)

        store.create_session(SAMPLE_MD, MockLLM())
        store.create_session(SAMPLE_MD, MockLLM())

        import time
        time.sleep(0.01)
        removed = store.cleanup_expired()
        assert removed == 2
        assert store.count() == 0

    def test_list_session_ids(self):
        from backend.core.session import SessionStore

        store = SessionStore()

        cid1, _ = store.create_session(SAMPLE_MD, MockLLM())
        cid2, _ = store.create_session(SAMPLE_MD, MockLLM())

        ids = store.list_session_ids()
        assert cid1 in ids
        assert cid2 in ids

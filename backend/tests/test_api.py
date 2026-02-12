"""
Integration tests for the FastAPI API layer.

Tests cover:
- POST /api/validate-schema with valid and invalid schemas
- POST /api/chat full conversation flow (with mock LLM)
- Session persistence across multiple /chat calls
- Error responses for malformed requests
- GET /api/schemas listing
- GET /api/schemas/{filename}
- POST /api/sessions/reset
- GET /api/health
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.api.routes import configure_routes, router
from backend.core.session import SessionStore

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# --- Mock LLM for integration tests ---


class MockLLM:
    """Mock LLM that returns pre-configured JSON responses."""

    def __init__(self, responses: list[dict] | None = None):
        self.responses = list(responses or [])
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        if not self.responses:
            # Default: return an answer intent for the next field
            response_dict = {
                "intent": "answer",
                "field_id": "leave_type",
                "value": "Annual",
                "message": "Got it!",
            }
        else:
            response_dict = self.responses.pop(0)
        result = MagicMock()
        result.content = json.dumps(response_dict)
        return result


# --- Fixtures ---


def _load_leave_schema() -> dict:
    """Load the leave_request schema as a dict."""
    with open(SCHEMAS_DIR / "leave_request.json") as f:
        return json.load(f)


def _create_test_app(llm=None):
    """Create a FastAPI test client with a mock LLM."""
    from fastapi import FastAPI

    app = FastAPI()
    session_store = SessionStore(timeout_seconds=3600)
    mock_llm = llm or MockLLM()
    configure_routes(session_store, mock_llm)
    app.include_router(router, prefix="/api")
    return TestClient(app), session_store, mock_llm


# --- /api/validate-schema tests ---


class TestValidateSchema:
    """Tests for the POST /api/validate-schema endpoint."""

    def test_valid_schema(self):
        client, _, _ = _create_test_app()
        schema = _load_leave_schema()
        response = client.post("/api/validate-schema", json={"form_schema": schema})
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_invalid_schema_missing_fields(self):
        client, _, _ = _create_test_app()
        response = client.post(
            "/api/validate-schema",
            json={"form_schema": {"form_id": "test"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_invalid_schema_duplicate_ids(self):
        client, _, _ = _create_test_app()
        schema = {
            "form_id": "test",
            "fields": [
                {"id": "f1", "type": "text", "required": True, "prompt": "First"},
                {"id": "f1", "type": "text", "required": True, "prompt": "Duplicate"},
            ],
        }
        response = client.post("/api/validate-schema", json={"form_schema": schema})
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any("duplicate" in e.lower() or "unique" in e.lower() for e in data["errors"])

    def test_invalid_schema_bad_visible_if_reference(self):
        client, _, _ = _create_test_app()
        schema = {
            "form_id": "test",
            "fields": [
                {"id": "f1", "type": "text", "required": True, "prompt": "First"},
                {
                    "id": "f2",
                    "type": "text",
                    "required": True,
                    "prompt": "Second",
                    "visible_if": {
                        "all": [{"field": "nonexistent", "operator": "EXISTS"}]
                    },
                },
            ],
        }
        response = client.post("/api/validate-schema", json={"form_schema": schema})
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    def test_validate_schema_empty_body(self):
        client, _, _ = _create_test_app()
        response = client.post("/api/validate-schema", json={})
        # FastAPI returns 422 for missing required fields
        assert response.status_code == 422

    def test_invalid_field_type(self):
        client, _, _ = _create_test_app()
        schema = {
            "form_id": "test",
            "fields": [
                {"id": "f1", "type": "invalid_type", "required": True, "prompt": "Bad type"},
            ],
        }
        response = client.post("/api/validate-schema", json={"form_schema": schema})
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False


# --- /api/chat tests ---


class TestChat:
    """Tests for the POST /api/chat endpoint."""

    def test_first_message_creates_session(self):
        """First chat message should create a new session and return an action."""
        mock_llm = MockLLM([
            {"intent": "answer", "field_id": "leave_type", "value": "Annual", "message": "Got it!"}
        ])
        client, store, _ = _create_test_app(mock_llm)
        schema = _load_leave_schema()

        response = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "I want annual leave",
        })

        assert response.status_code == 200
        data = response.json()
        assert "conversation_id" in data
        assert "action" in data
        assert "answers" in data
        # Session should exist in the store
        assert store.count() == 1

    def test_empty_first_message_returns_initial_action(self):
        """Empty first message should return the initial greeting action."""
        client, store, _ = _create_test_app()
        schema = _load_leave_schema()

        response = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "",
        })

        assert response.status_code == 200
        data = response.json()
        assert "conversation_id" in data
        assert "action" in data
        # Initial action should be a greeting or first question
        action = data["action"]
        assert "action" in action  # action key holds the action type (e.g. ASK_DROPDOWN)

    def test_session_persistence(self):
        """Multiple messages with the same conversation_id should use the same session."""
        mock_llm = MockLLM([
            {"intent": "answer", "field_id": "leave_type", "value": "Annual", "message": "Got it!"},
            {"intent": "answer", "field_id": "start_date", "value": "2026-03-01", "message": "Start date set."},
        ])
        client, store, _ = _create_test_app(mock_llm)
        schema = _load_leave_schema()

        # First message
        r1 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "I want annual leave",
        })
        cid = r1.json()["conversation_id"]
        assert store.count() == 1

        # Second message with same conversation_id
        r2 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "Starting March 1st",
            "conversation_id": cid,
        })
        assert r2.status_code == 200
        # Should still be 1 session (reused)
        assert store.count() == 1

    def test_invalid_schema_returns_400(self):
        """Chat with an invalid schema should return 400."""
        client, _, _ = _create_test_app()

        response = client.post("/api/chat", json={
            "form_schema": {"bad": "schema"},
            "user_message": "Hello",
        })

        assert response.status_code == 400
        assert "Invalid form schema" in response.json()["detail"]

    def test_chat_missing_body_fields(self):
        """Chat with missing required fields should return 422."""
        client, _, _ = _create_test_app()

        response = client.post("/api/chat", json={})
        assert response.status_code == 422

    def test_custom_conversation_id(self):
        """Client can provide a custom conversation_id."""
        mock_llm = MockLLM([
            {"intent": "answer", "field_id": "leave_type", "value": "Sick", "message": "Ok."}
        ])
        client, store, _ = _create_test_app(mock_llm)
        schema = _load_leave_schema()
        custom_id = "my-custom-session-123"

        response = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "Sick leave",
            "conversation_id": custom_id,
        })

        assert response.status_code == 200
        assert response.json()["conversation_id"] == custom_id
        assert store.get_session(custom_id) is not None


# --- /api/schemas tests ---


class TestSchemas:
    """Tests for the GET /api/schemas endpoint."""

    def test_list_schemas(self):
        client, _, _ = _create_test_app()
        response = client.get("/api/schemas")
        assert response.status_code == 200
        data = response.json()
        assert "schemas" in data
        assert len(data["schemas"]) >= 2  # leave_request + incident_report

    def test_get_specific_schema(self):
        client, _, _ = _create_test_app()
        response = client.get("/api/schemas/leave_request.json")
        assert response.status_code == 200
        data = response.json()
        assert data["form_id"] == "leave_request"
        assert "fields" in data

    def test_get_nonexistent_schema(self):
        client, _, _ = _create_test_app()
        response = client.get("/api/schemas/nonexistent.json")
        assert response.status_code == 404


# --- /api/sessions/reset tests ---


class TestSessionReset:
    """Tests for the POST /api/sessions/reset endpoint."""

    def test_reset_existing_session(self):
        mock_llm = MockLLM([
            {"intent": "answer", "field_id": "leave_type", "value": "Annual", "message": "Ok"}
        ])
        client, store, _ = _create_test_app(mock_llm)
        schema = _load_leave_schema()

        # Create a session
        r = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "Annual leave",
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
        from backend.core.schema import FormSchema
        from backend.core.session import SessionStore

        store = SessionStore(timeout_seconds=0)  # Immediate expiry
        schema = FormSchema(**_load_leave_schema())
        cid, session = store.create_session(schema, MockLLM())

        # Session should immediately be expired
        import time
        time.sleep(0.01)
        assert store.get_session(cid) is None

    def test_cleanup_expired(self):
        from backend.core.schema import FormSchema
        from backend.core.session import SessionStore

        store = SessionStore(timeout_seconds=0)
        schema = FormSchema(**_load_leave_schema())

        store.create_session(schema, MockLLM())
        store.create_session(schema, MockLLM())

        import time
        time.sleep(0.01)
        removed = store.cleanup_expired()
        assert removed == 2
        assert store.count() == 0

    def test_list_session_ids(self):
        from backend.core.schema import FormSchema
        from backend.core.session import SessionStore

        store = SessionStore()
        schema = FormSchema(**_load_leave_schema())

        cid1, _ = store.create_session(schema, MockLLM())
        cid2, _ = store.create_session(schema, MockLLM())

        ids = store.list_session_ids()
        assert cid1 in ids
        assert cid2 in ids

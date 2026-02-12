"""
API-level end-to-end tests.

Tests multi-turn conversations through the /api/chat HTTP endpoint,
verifying session persistence, answer accumulation, and full form completion.
Accounts for the two-phase flow: greeting MESSAGE → extraction → follow-up.

Uses mock LLM injected via configure_routes.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import configure_routes, router
from backend.core.session import SessionStore

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


# --- Mock LLM ---


class SequenceMockLLM:
    """Mock LLM returning predefined responses in sequence."""

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        if not self.responses:
            # Default fallback
            result = MagicMock()
            result.content = json.dumps({
                "intent": "clarify",
                "message": "Could you repeat that?",
            })
            return result
        response_dict = self.responses.pop(0)
        result = MagicMock()
        result.content = json.dumps(response_dict)
        return result


def _load_schema(name: str) -> dict:
    with open(SCHEMAS_DIR / f"{name}.json") as f:
        return json.load(f)


def _create_app(llm) -> tuple[TestClient, SessionStore]:
    app = FastAPI()
    store = SessionStore()
    configure_routes(store, llm)
    app.include_router(router, prefix="/api")
    return TestClient(app), store


# --- Multi-turn conversation tests ---


class TestMultiTurnConversation:
    """Full multi-turn conversations through the HTTP API."""

    def test_full_leave_request_via_api(self):
        """Complete a leave request form through multiple API calls."""
        llm = SequenceMockLLM([
            # Extraction: captures leave_type and start_date
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual", "start_date": "2026-03-01"},
             "message": "Captured leave type and start date."},
            # Follow-up: end_date
            {"intent": "answer", "field_id": "end_date", "value": "2026-03-05",
             "message": "End date set."},
            # Follow-up: reason
            {"intent": "answer", "field_id": "reason", "value": "Holiday",
             "message": "Reason recorded."},
        ])
        client, store = _create_app(llm)
        schema = _load_schema("leave_request")

        # Turn 0: Initialize session — should return MESSAGE greeting
        r0 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "",
        })
        assert r0.status_code == 200
        cid = r0.json()["conversation_id"]
        assert r0.json()["action"]["action"] == "MESSAGE"

        # Turn 1: User sends description — extraction
        r1 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "Annual leave starting March 1st",
            "conversation_id": cid,
        })
        assert r1.status_code == 200
        assert r1.json()["action"]["action"] == "ASK_DATE"
        assert r1.json()["action"]["field_id"] == "end_date"
        assert r1.json()["answers"]["leave_type"] == "Annual"
        assert r1.json()["conversation_id"] == cid

        # Turn 2: end_date
        r2 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "March 5th",
            "conversation_id": cid,
        })
        assert r2.json()["action"]["field_id"] == "reason"

        # Turn 3: reason → FORM_COMPLETE
        r3 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "Holiday",
            "conversation_id": cid,
        })
        assert r3.json()["action"]["action"] == "FORM_COMPLETE"
        data = r3.json()["action"]["data"]
        assert data["leave_type"] == "Annual"
        assert data["start_date"] == "2026-03-01"
        assert data["reason"] == "Holiday"

    def test_session_survives_multiple_turns(self):
        """Verify session state persists across API calls."""
        llm = SequenceMockLLM([
            # Extraction
            {"intent": "multi_answer",
             "answers": {"leave_type": "Sick"},
             "message": "Sick leave."},
            # Follow-up
            {"intent": "answer", "field_id": "start_date", "value": "2026-04-01",
             "message": "Start date."},
        ])
        client, store = _create_app(llm)
        schema = _load_schema("leave_request")

        # Init
        r0 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "",
        })
        cid = r0.json()["conversation_id"]

        # Turn 1: extraction
        r1 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "Sick leave",
            "conversation_id": cid,
        })
        assert r1.json()["answers"] == {"leave_type": "Sick"}

        # Turn 2: follow-up
        r2 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "April 1st",
            "conversation_id": cid,
        })
        answers = r2.json()["answers"]
        assert answers["leave_type"] == "Sick"
        assert answers["start_date"] == "2026-04-01"

        # Only 1 session in the store
        assert store.count() == 1

    def test_reset_and_restart(self):
        """Reset a session and start fresh."""
        llm = SequenceMockLLM([
            # Extraction
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual"},
             "message": "Annual."},
        ])
        client, store = _create_app(llm)
        schema = _load_schema("leave_request")

        # Init and answer via extraction
        r0 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "",
        })
        cid = r0.json()["conversation_id"]

        r1 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "Annual",
            "conversation_id": cid,
        })
        assert r1.json()["answers"]["leave_type"] == "Annual"

        # Reset
        r_reset = client.post("/api/sessions/reset", json={
            "conversation_id": cid,
        })
        assert r_reset.json()["success"] is True
        assert store.count() == 0

        # Start fresh — same schema but new session
        r_new = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "",
        })
        new_cid = r_new.json()["conversation_id"]
        assert new_cid != cid  # Different session
        assert r_new.json()["answers"] == {}

    def test_two_parallel_sessions(self):
        """Two independent conversations can run simultaneously."""
        llm = SequenceMockLLM([
            # Session 1 extraction: annual leave
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual"},
             "message": "Annual."},
            # Session 2 extraction: sick leave
            {"intent": "multi_answer",
             "answers": {"leave_type": "Sick"},
             "message": "Sick."},
        ])
        client, store = _create_app(llm)
        schema = _load_schema("leave_request")

        # Init session 1
        r1_init = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "",
        })
        cid1 = r1_init.json()["conversation_id"]

        # Init session 2
        r2_init = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "",
        })
        cid2 = r2_init.json()["conversation_id"]

        assert cid1 != cid2
        assert store.count() == 2

        # Answer in session 1 (extraction)
        r1_a = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "Annual",
            "conversation_id": cid1,
        })
        assert r1_a.json()["answers"]["leave_type"] == "Annual"

        # Answer in session 2 (extraction)
        r2_a = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "Sick",
            "conversation_id": cid2,
        })
        assert r2_a.json()["answers"]["leave_type"] == "Sick"

        # Sessions remain independent
        assert store.count() == 2


class TestApiErrorHandling:
    """API error handling with multi-turn context."""

    def test_expired_session_creates_new(self):
        """Using an expired session ID creates a new session."""
        llm = SequenceMockLLM([
            # New session: extraction
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual"},
             "message": "Annual."},
        ])
        # Session timeout = 0 for immediate expiry
        app = FastAPI()
        store = SessionStore(timeout_seconds=0)
        configure_routes(store, llm)
        app.include_router(router, prefix="/api")
        client = TestClient(app)
        schema = _load_schema("leave_request")

        # Create and immediately expire
        r0 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "",
        })
        old_cid = r0.json()["conversation_id"]

        import time
        time.sleep(0.01)

        # Try to use expired session — should create new
        r1 = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "Annual leave",
            "conversation_id": old_cid,
        })
        assert r1.status_code == 200
        # Should have answers from extraction
        assert r1.json()["answers"].get("leave_type") == "Annual"

    def test_malformed_schema_in_chat(self):
        """Sending invalid schema to /chat returns 400."""
        llm = SequenceMockLLM([])
        client, _ = _create_app(llm)

        r = client.post("/api/chat", json={
            "form_schema": {"not": "a valid schema"},
            "user_message": "Hello",
        })
        assert r.status_code == 400

    def test_validate_then_chat(self):
        """Validate a schema, then use it for chat."""
        llm = SequenceMockLLM([])
        client, _ = _create_app(llm)
        schema = _load_schema("leave_request")

        # Validate first
        rv = client.post("/api/validate-schema", json={"form_schema": schema})
        assert rv.json()["valid"] is True

        # Use for chat — initial greeting MESSAGE
        rc = client.post("/api/chat", json={
            "form_schema": schema,
            "user_message": "",
        })
        assert rc.status_code == 200
        assert rc.json()["action"]["action"] == "MESSAGE"

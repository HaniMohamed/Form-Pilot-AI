"""
API-level end-to-end tests.

Tests multi-turn conversations through the /api/chat HTTP endpoint,
verifying session persistence, answer accumulation, and tool call round-trips.

Uses mock LLM injected via configure_routes.
"""

import json
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import configure_routes, router
from backend.core.session import SessionStore


SAMPLE_MD = """
# Leave Request Form

## Fields
- **leave_type** (dropdown, required): Type of leave?
  Options: Annual, Sick, Emergency
- **start_date** (date, required): Start date?
- **end_date** (date, required): End date?
- **reason** (text, required): Reason for leave?
"""

TOOL_FORM_MD = """
# Injury Report

## Tools
- `get_establishments`: Returns establishments list

## Fields
- **establishment** (dropdown, required): Select establishment
- **description** (text, required): Describe injury
"""


# --- Mock LLM ---


class SequenceMockLLM:
    """Mock LLM returning predefined responses in sequence."""

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.call_count = 0

    async def ainvoke(self, messages, **kwargs):
        self.call_count += 1
        if not self.responses:
            result = MagicMock()
            result.content = json.dumps({
                "action": "MESSAGE",
                "text": "Could you repeat that?",
            })
            return result
        response_dict = self.responses.pop(0)
        result = MagicMock()
        result.content = json.dumps(response_dict)
        return result


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
            # Conversation: ask end_date
            {"action": "ASK_DATE", "field_id": "end_date",
             "label": "End date?",
             "message": "When does it end?"},
            # Follow-up: answer end_date
            {"action": "ASK_TEXT", "field_id": "reason",
             "label": "Reason?",
             "message": "What's the reason?"},
            # Follow-up: answer reason → FORM_COMPLETE
            {"action": "FORM_COMPLETE",
             "data": {"leave_type": "Annual", "start_date": "2026-03-01",
                      "end_date": "2026-03-05", "reason": "Holiday"},
             "message": "All done!"},
        ])
        client, store = _create_app(llm)

        # Turn 0: Initialize session
        r0 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "",
        })
        assert r0.status_code == 200
        cid = r0.json()["conversation_id"]
        assert r0.json()["action"]["action"] == "MESSAGE"

        # Turn 1: Extraction
        r1 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "Annual leave starting March 1st",
            "conversation_id": cid,
        })
        assert r1.status_code == 200
        assert r1.json()["action"]["action"] == "ASK_DATE"
        assert r1.json()["answers"]["leave_type"] == "Annual"

        # Turn 2: end_date
        r2 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "March 5th",
            "conversation_id": cid,
        })
        assert r2.json()["action"]["field_id"] == "reason"

        # Turn 3: reason → FORM_COMPLETE
        r3 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "Holiday",
            "conversation_id": cid,
        })
        assert r3.json()["action"]["action"] == "FORM_COMPLETE"

    def test_session_survives_multiple_turns(self):
        """Verify session state persists across API calls."""
        llm = SequenceMockLLM([
            {"intent": "multi_answer",
             "answers": {"leave_type": "Sick"},
             "message": "Sick leave."},
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start date?",
             "message": "When?"},
            {"action": "ASK_DATE", "field_id": "end_date",
             "label": "End date?",
             "message": "End?"},
        ])
        client, store = _create_app(llm)

        # Init
        r0 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "",
        })
        cid = r0.json()["conversation_id"]

        # Turn 1: extraction
        r1 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "Sick leave",
            "conversation_id": cid,
        })
        assert r1.json()["answers"]["leave_type"] == "Sick"

        # Turn 2: follow-up
        r2 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "April 1st",
            "conversation_id": cid,
        })
        assert r2.status_code == 200
        assert store.count() == 1

    def test_reset_and_restart(self):
        """Reset a session and start fresh."""
        llm = SequenceMockLLM([
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual"},
             "message": "Annual."},
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start?", "message": "When?"},
        ])
        client, store = _create_app(llm)

        # Init and answer
        r0 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "",
        })
        cid = r0.json()["conversation_id"]

        r1 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
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

        # Start fresh
        r_new = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "",
        })
        new_cid = r_new.json()["conversation_id"]
        assert new_cid != cid
        assert r_new.json()["answers"] == {}

    def test_two_parallel_sessions(self):
        """Two independent conversations can run simultaneously."""
        llm = SequenceMockLLM([
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual"},
             "message": "Annual."},
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start?", "message": "When?"},
            {"intent": "multi_answer",
             "answers": {"leave_type": "Sick"},
             "message": "Sick."},
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start?", "message": "When?"},
        ])
        client, store = _create_app(llm)

        # Init session 1
        r1_init = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "",
        })
        cid1 = r1_init.json()["conversation_id"]

        # Init session 2
        r2_init = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "",
        })
        cid2 = r2_init.json()["conversation_id"]

        assert cid1 != cid2
        assert store.count() == 2

        # Answer in session 1
        r1_a = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "Annual",
            "conversation_id": cid1,
        })
        assert r1_a.json()["answers"]["leave_type"] == "Annual"

        # Answer in session 2
        r2_a = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "Sick",
            "conversation_id": cid2,
        })
        assert r2_a.json()["answers"]["leave_type"] == "Sick"


class TestToolCallViaApi:
    """Test tool call round-trips through the HTTP API."""

    def test_tool_call_and_result_via_api(self):
        """Tool call returned by LLM → frontend sends results → LLM continues."""
        llm = SequenceMockLLM([
            # Extraction
            {"intent": "multi_answer", "answers": {},
             "message": "Need data first."},
            # Conversation: tool call
            {"action": "TOOL_CALL", "tool_name": "get_establishments",
             "tool_args": {}, "message": "Fetching establishments..."},
            # After tool results: ask field
            {"action": "ASK_DROPDOWN", "field_id": "establishment",
             "label": "Select",
             "options": ["Company A"],
             "message": "Select your establishment."},
        ])
        client, store = _create_app(llm)

        # Init
        r0 = client.post("/api/chat", json={
            "form_context_md": TOOL_FORM_MD,
            "user_message": "",
        })
        cid = r0.json()["conversation_id"]

        # User message → extraction → tool call
        r1 = client.post("/api/chat", json={
            "form_context_md": TOOL_FORM_MD,
            "user_message": "Report injury",
            "conversation_id": cid,
        })
        assert r1.json()["action"]["action"] == "TOOL_CALL"
        assert r1.json()["action"]["tool_name"] == "get_establishments"

        # Send tool results
        r2 = client.post("/api/chat", json={
            "form_context_md": TOOL_FORM_MD,
            "user_message": "",
            "conversation_id": cid,
            "tool_results": [{
                "tool_name": "get_establishments",
                "result": {"establishments": ["Company A"]},
            }],
        })
        assert r2.json()["action"]["action"] == "ASK_DROPDOWN"
        assert r2.json()["action"]["field_id"] == "establishment"


class TestApiErrorHandling:
    """API error handling."""

    def test_expired_session_creates_new(self):
        """Using an expired session ID creates a new session."""
        llm = SequenceMockLLM([
            {"intent": "multi_answer",
             "answers": {"leave_type": "Annual"},
             "message": "Annual."},
            {"action": "ASK_DATE", "field_id": "start_date",
             "label": "Start?", "message": "When?"},
        ])
        app = FastAPI()
        store = SessionStore(timeout_seconds=0)
        configure_routes(store, llm)
        app.include_router(router, prefix="/api")
        client = TestClient(app)

        # Create and immediately expire
        r0 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "",
        })
        old_cid = r0.json()["conversation_id"]

        import time
        time.sleep(0.01)

        # Try to use expired session → creates new
        r1 = client.post("/api/chat", json={
            "form_context_md": SAMPLE_MD,
            "user_message": "Annual leave",
            "conversation_id": old_cid,
        })
        assert r1.status_code == 200
        assert r1.json()["answers"].get("leave_type") == "Annual"

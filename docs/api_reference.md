# API Reference

The FormPilot AI backend exposes a REST API under the `/api` prefix.

**Base URL:** `http://localhost:8000/api`

**Start the server:**

```bash
uvicorn backend.api.app:app --reload
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Process a user message in a form-filling conversation |
| GET | `/api/schemas` | List available example form definitions (markdown) |
| GET | `/api/schemas/{filename}` | Get a specific form definition markdown |
| POST | `/api/sessions/reset` | Reset/delete a conversation session |
| GET | `/api/health` | Health check |

---

## POST /api/chat

Process a user message in a form-filling conversation. Creates a new session on first call, or resumes an existing one.

### Conversation Flow

1. **First call** — Send empty `user_message` with the form markdown. Returns a greeting MESSAGE.
2. **Second call** — User provides a free-text description. AI extracts all possible field values (bulk extraction).
3. **Subsequent calls** — AI asks for remaining missing fields one at a time, possibly issuing TOOL_CALL actions.
4. **Tool results** — If AI returns a TOOL_CALL, the frontend executes the tool and sends back `tool_results`.
5. **Completion** — Once all required fields are collected, AI returns FORM_COMPLETE.

### Request

```json
{
  "form_context_md": "# Report Injury\n\n## Fields\n- injury_date (date): ...",
  "user_message": "I got injured at work yesterday",
  "conversation_id": "optional-uuid-string",
  "tool_results": [
    {
      "tool_name": "get_establishments",
      "result": { "establishments": [...] }
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `form_context_md` | string | Yes | The form definition as markdown content |
| `user_message` | string | Yes | The user's message (empty string for initial greeting) |
| `conversation_id` | string | No | Session ID to resume. Auto-generated if omitted. |
| `tool_results` | array | No | Results from tool calls requested by the AI |

### Response

```json
{
  "action": {
    "action": "ASK_DROPDOWN",
    "field_id": "establishment",
    "label": "Which establishment?",
    "options": ["Riyadh Technology Co.", "Jeddah Manufacturing Ltd."],
    "message": "Please select your establishment."
  },
  "conversation_id": "abc-123-def",
  "answers": {
    "injury_date": "2026-01-15"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | object | The AI's response action (see [Action Protocol](action_protocol.md)) |
| `conversation_id` | string | Session ID for subsequent calls |
| `answers` | object | All currently collected answers |

### Tool Call Response

When the AI needs data from the frontend (e.g. dropdown options from an API):

```json
{
  "action": {
    "action": "TOOL_CALL",
    "tool_name": "get_establishments",
    "tool_args": {},
    "message": "Looking up your establishments..."
  },
  "conversation_id": "abc-123-def",
  "answers": {}
}
```

The frontend should execute the tool and send the results back:

```json
{
  "form_context_md": "...",
  "user_message": "",
  "conversation_id": "abc-123-def",
  "tool_results": [
    {
      "tool_name": "get_establishments",
      "result": {
        "establishments": [
          {"registrationNo": "5001234567", "name": {"english": "Riyadh Technology Co."}}
        ]
      }
    }
  ]
}
```

### Error Responses

| Status | Condition |
|--------|-----------|
| 422 | Missing required request fields |
| 500 | Server configuration error or LLM failure |

### Example: Complete Flow

```bash
# Step 1: Initialize — greeting
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "form_context_md": "# Leave Request\n\n## Fields\n...",
    "user_message": ""
  }'
# Returns: {"action": {"action": "MESSAGE", "text": "Hello! ..."}, ...}

# Step 2: Bulk extraction
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "form_context_md": "# Leave Request\n\n## Fields\n...",
    "user_message": "Annual leave from March 1st to March 10th for vacation",
    "conversation_id": "abc-123"
  }'
# Returns: {"action": {"action": "FORM_COMPLETE", "data": {...}}, ...}
```

---

## GET /api/schemas

List available example form definition files from `backend/schemas/`.

### Response

```json
{
  "schemas": [
    {
      "filename": "form_pilot_report_injury.md",
      "title": "Report Occupational Injury",
      "size": 4532
    },
    {
      "filename": "leave_request.md",
      "title": "Leave Request",
      "size": 2100
    }
  ]
}
```

---

## GET /api/schemas/{filename}

Get the full content of a specific form definition.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `filename` | string (path) | Form definition filename (e.g., `form_pilot_report_injury.md`) |

### Response

```json
{
  "filename": "form_pilot_report_injury.md",
  "content": "# Report Occupational Injury\n\n## Fields\n..."
}
```

### Error Responses

| Status | Condition |
|--------|-----------|
| 404 | File not found |

---

## POST /api/sessions/reset

Delete a conversation session and all its state.

### Request

```json
{
  "conversation_id": "abc-123-def"
}
```

### Response

```json
{
  "success": true,
  "message": "Session reset"
}
```

Or if session not found:

```json
{
  "success": false,
  "message": "Session not found"
}
```

---

## GET /api/health

Health check endpoint.

### Response

```json
{
  "status": "healthy",
  "active_sessions": 3
}
```

---

## Configuration

The backend is configured via environment variables. See `.env.example` for all options.

### Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `openai` | LLM provider: `openai`, `azure_openai`, `watsonx`, `custom` |
| `SESSION_TIMEOUT_SECONDS` | `1800` | Session expiry time (30 minutes) |
| `CORS_ALLOWED_ORIGINS` | `*` | Comma-separated allowed origins |
| `BACKEND_HOST` | `0.0.0.0` | Server host |
| `BACKEND_PORT` | `8000` | Server port |

### CORS

In development, all origins are allowed. For production, set `CORS_ALLOWED_ORIGINS` to your frontend URL(s).

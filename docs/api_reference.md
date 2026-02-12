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
| POST | `/api/validate-schema` | Validate a form schema JSON |
| GET | `/api/schemas` | List available example schemas |
| GET | `/api/schemas/{filename}` | Get a specific example schema |
| POST | `/api/sessions/reset` | Reset/delete a conversation session |
| GET | `/api/health` | Health check |

---

## POST /api/chat

Process a user message in a form-filling conversation. Creates a new session on first call, or resumes an existing one.

### Conversation Flow

1. **First call** — Send empty `user_message` with the schema. Returns a greeting MESSAGE.
2. **Second call** — User provides a free-text description. AI extracts all possible field values (bulk extraction).
3. **Subsequent calls** — AI asks for remaining missing fields one at a time until FORM_COMPLETE.

### Request

```json
{
  "form_schema": {
    "form_id": "leave_request",
    "fields": [...]
  },
  "user_message": "I want annual leave starting March 1st",
  "conversation_id": "optional-uuid-string"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `form_schema` | object | Yes | The form schema JSON (see [Schema Guide](schema_guide.md)) |
| `user_message` | string | Yes | The user's message (empty string for initial greeting) |
| `conversation_id` | string | No | Session ID to resume. Auto-generated if omitted. |

### Response

```json
{
  "action": {
    "action": "ASK_DATE",
    "field_id": "end_date",
    "label": "When does your leave end?",
    "message": "I captured your leave type and start date. When does your leave end?"
  },
  "conversation_id": "abc-123-def",
  "answers": {
    "leave_type": "Annual",
    "start_date": "2026-03-01"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | object | The AI's response action (see [Action Protocol](action_protocol.md)) |
| `conversation_id` | string | Session ID for subsequent calls |
| `answers` | object | All currently visible answers |

### Error Responses

| Status | Condition |
|--------|-----------|
| 400 | Invalid form schema |
| 422 | Missing required request fields |
| 500 | Server configuration error or LLM failure |

### Example: Complete Flow

```bash
# Step 1: Initialize — greeting
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "form_schema": {"form_id": "leave_request", "fields": [...]},
    "user_message": ""
  }'
# Returns: {"action": {"action": "MESSAGE", "text": "Hello! ..."}, ...}

# Step 2: Bulk extraction
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "form_schema": {"form_id": "leave_request", "fields": [...]},
    "user_message": "Annual leave from March 1st to March 10th for vacation",
    "conversation_id": "abc-123"
  }'
# Returns: {"action": {"action": "FORM_COMPLETE", "data": {...}}, ...}
```

---

## POST /api/validate-schema

Validate a form schema JSON structure without starting a conversation.

### Request

```json
{
  "form_schema": {
    "form_id": "my_form",
    "fields": [...]
  }
}
```

### Response

```json
{
  "valid": true,
  "errors": []
}
```

Or on failure:

```json
{
  "valid": false,
  "errors": [
    "fields → 1 → id: Duplicate field ID 'name'",
    "fields → 2 → visible_if → all → 0 → field: References non-existent field 'xyz'"
  ]
}
```

---

## GET /api/schemas

List available example schema files from `backend/schemas/`.

### Response

```json
{
  "schemas": [
    {
      "filename": "incident_report.json",
      "form_id": "incident_report",
      "field_count": 5
    },
    {
      "filename": "leave_request.json",
      "form_id": "leave_request",
      "field_count": 7
    }
  ]
}
```

---

## GET /api/schemas/{filename}

Get the full content of a specific example schema.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `filename` | string (path) | Schema filename (e.g., `leave_request.json`) |

### Response

Returns the raw JSON schema object.

### Error Responses

| Status | Condition |
|--------|-----------|
| 404 | Schema file not found |

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

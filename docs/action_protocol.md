# AI Action Protocol

FormPilot AI communicates with the Flutter web app through structured JSON actions. Each action tells the UI what to render and how to interact with the user.

## Action Types

| Action | Description | When Used |
|--------|-------------|-----------|
| `MESSAGE` | Display a text message | Greeting, extraction summary, errors |
| `ASK_DROPDOWN` | Render a dropdown selector | Asking for a dropdown field |
| `ASK_CHECKBOX` | Render a checkbox group | Asking for a checkbox field |
| `ASK_TEXT` | Render a text input | Asking for a text field |
| `ASK_DATE` | Render a date picker | Asking for a date field |
| `ASK_DATETIME` | Render a date+time picker | Asking for a datetime field |
| `ASK_LOCATION` | Render a location picker | Asking for a location field |
| `TOOL_CALL` | Request the frontend to execute a tool | AI needs external data (e.g. API lookup) |
| `FORM_COMPLETE` | Display final data summary | All required fields filled |

## Action JSON Formats

### MESSAGE

Displayed as a conversational message in the chat panel. Used for greetings, extraction summaries, clarifications, and error messages.

```json
{
  "action": "MESSAGE",
  "text": "Hello! I'm FormPilot AI, your form-filling assistant. Please describe all the information you'd like to fill in."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | `"MESSAGE"` | Action type identifier |
| `text` | string | The message text to display |

### ASK_DROPDOWN

Asks the user to select one option from a list.

```json
{
  "action": "ASK_DROPDOWN",
  "field_id": "incident_type",
  "label": "What is the incident type?",
  "options": ["Fire", "Accident", "Injury"],
  "message": "Please select the incident type from the list."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | `"ASK_DROPDOWN"` | Action type identifier |
| `field_id` | string | The field this action is for |
| `label` | string | Question text (from field `prompt`) |
| `options` | array of strings | Available choices |
| `message` | string | Conversational message (optional) |

**Expected answer format:** A single string matching one of the options exactly.

### ASK_CHECKBOX

Asks the user to select one or more options.

```json
{
  "action": "ASK_CHECKBOX",
  "field_id": "medical_certificate",
  "label": "Do you have a medical certificate?",
  "options": ["Yes", "No"],
  "message": "Please select whether you have a medical certificate."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | `"ASK_CHECKBOX"` | Action type identifier |
| `field_id` | string | The field this action is for |
| `label` | string | Question text |
| `options` | array of strings | Available choices |
| `message` | string | Conversational message (optional) |

**Expected answer format:** An array of selected option strings, e.g., `["Yes"]`.

### ASK_TEXT

Asks the user to enter free text.

```json
{
  "action": "ASK_TEXT",
  "field_id": "reason",
  "label": "Please provide a reason for your leave",
  "message": "What is the reason for your leave request?"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | `"ASK_TEXT"` | Action type identifier |
| `field_id` | string | The field this action is for |
| `label` | string | Question text |
| `message` | string | Conversational message (optional) |

**Expected answer format:** A non-empty string.

### ASK_DATE

Asks the user to select a date.

```json
{
  "action": "ASK_DATE",
  "field_id": "start_date",
  "label": "When does your leave start?",
  "message": "Please select or type your start date."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | `"ASK_DATE"` | Action type identifier |
| `field_id` | string | The field this action is for |
| `label` | string | Question text |
| `message` | string | Conversational message (optional) |

**Expected answer format:** ISO 8601 date string: `"YYYY-MM-DD"` (e.g., `"2026-03-01"`).

### ASK_DATETIME

Asks the user to select a date and time.

```json
{
  "action": "ASK_DATETIME",
  "field_id": "meeting_time",
  "label": "When is the meeting?",
  "message": "Please select the date and time."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | `"ASK_DATETIME"` | Action type identifier |
| `field_id` | string | The field this action is for |
| `label` | string | Question text |
| `message` | string | Conversational message (optional) |

**Expected answer format:** ISO 8601 datetime string: `"YYYY-MM-DDTHH:MM:SS"` (e.g., `"2026-03-01T14:30:00"`).

### ASK_LOCATION

Asks the user to provide a geographic location.

```json
{
  "action": "ASK_LOCATION",
  "field_id": "location",
  "label": "Please select the incident location",
  "message": "Where did the incident occur?"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | `"ASK_LOCATION"` | Action type identifier |
| `field_id` | string | The field this action is for |
| `label` | string | Question text |
| `message` | string | Conversational message (optional) |

**Expected answer format:** Object with latitude and longitude:

```json
{"lat": 24.7136, "lng": 46.6753}
```

- `lat` must be between -90 and 90
- `lng` must be between -180 and 180

### TOOL_CALL

Requests the frontend to execute a tool (e.g. data lookup, API call). The frontend should execute the tool and send the results back in the next `/api/chat` request via `tool_results`.

```json
{
  "action": "TOOL_CALL",
  "tool_name": "get_establishments",
  "tool_args": {},
  "message": "Looking up your establishments..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | `"TOOL_CALL"` | Action type identifier |
| `tool_name` | string | Name of the tool to execute |
| `tool_args` | object | Arguments to pass to the tool (may be empty) |
| `message` | string | Status message to display while executing |

**Expected response:** The frontend sends `tool_results` in the next request:

```json
{
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

### FORM_COMPLETE

Signals that all required visible fields have been answered. Contains the final collected data.

```json
{
  "action": "FORM_COMPLETE",
  "data": {
    "incident_type": "Accident",
    "start_date": "2026-02-11",
    "end_date": "2026-02-15",
    "followup_reason": "Incident duration exceeded threshold",
    "location": {
      "lat": 24.7136,
      "lng": 46.6753
    }
  },
  "message": "All fields are complete! Here's a summary of your answers."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | `"FORM_COMPLETE"` | Action type identifier |
| `data` | object | All visible answered fields (field_id → value) |
| `message` | string | Completion summary message |

## Conversation Flow Diagram

```
User opens form
       │
       ▼
┌─────────────────┐
│  MESSAGE         │  ← AI greets user, asks for description
│  (greeting)      │
└────────┬────────┘
         │  User sends free-text description
         ▼
┌─────────────────┐
│  ASK_* / FORM_  │  ← AI extracts values, asks for missing fields
│  COMPLETE       │     or completes immediately
└────────┬────────┘
         │  (if missing fields)
         ▼
┌─────────────────┐
│  ASK_* /        │  ← One field at a time
│  TOOL_CALL      │     AI may request tool execution for data lookups
│  (field by      │
│   field)        │
└────────┬────────┘
         │  (repeat until all required fields answered)
         ▼
┌─────────────────┐
│  FORM_COMPLETE  │  ← Final data payload
└─────────────────┘
```

## LLM Intent Types

The LLM internally uses these intents to decide what action to return:

| Intent | Phase | Description |
|--------|-------|-------------|
| `multi_answer` | Extraction | Extracts multiple field values from free text |
| `answer` | Follow-up | Extracts a single field value from user message |
| `correction` | Follow-up | User wants to change a previous answer |
| `clarify` | Follow-up | User message is unclear, ask for clarification |
| `ask` | Follow-up | Present the next field question |

These intents are internal to the orchestrator — the Flutter app only sees the action types listed above.

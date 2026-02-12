# FormPilot AI

GenAI-powered conversational form filling system. An AI agent guides users through complex forms via chat, following structured schemas and deterministic business logic.

## Overview

FormPilot AI helps users fill complex forms through natural conversation. The AI:
- Asks one field at a time, in order
- Never assumes or fabricates values
- Follows deterministic visibility rules (not LLM-decided)
- Returns structured JSON actions to the UI
- Produces a final JSON payload for review and submission

## Architecture

```
┌──────────────────────┐     ┌──────────────────────┐     ┌─────────┐
│  Flutter Web App     │────▶│  Python Backend       │────▶│  LLM    │
│  (Simulation & Test) │◀────│  (FastAPI)            │◀────│  (API)  │
└──────────────────────┘     └──────────────────────┘     └─────────┘
        │                            │
   Chat Panel              Schema Validation
   Widget Rendering        Visibility Evaluator
   JSON Debug Panel        Form State Manager
                           Conversation Orchestrator
```

### Components

| Component | Purpose |
|-----------|---------|
| **Flutter Web App** | Simulation UI with chat, dynamic widgets, and debug panel |
| **Python Backend** | LangChain agent, form state, visibility evaluation, API |
| **LLM** | Reasoning and structured output only (no tool calling, no API access) |

## Project Structure

```
form_pilot_ai/
├── backend/                  # Python backend
│   ├── core/                 # Core logic (schema, visibility, state)
│   ├── agent/                # LangChain agent and orchestrator
│   ├── api/                  # FastAPI routes
│   ├── schemas/              # Example form schema JSON files
│   └── tests/                # Unit and integration tests
├── flutter_web/              # Flutter web app (simulation & testing)
│   └── lib/
│       ├── models/           # Dart data models (FormSchema, AIAction)
│       ├── screens/          # Simulation screen (three-panel layout)
│       ├── services/         # ChatService (backend HTTP communication)
│       └── widgets/          # Chat panel, dynamic widgets, debug panel
├── .env.example              # Environment variable template
└── .plan/                    # Project plan and TODO
```

## Setup

### Prerequisites

- Python 3.12+
- Flutter SDK (web enabled)
- An LLM API key (OpenAI, Azure OpenAI, or watsonx)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your LLM credentials:

```bash
cp .env.example .env
```

### Flutter Web App

```bash
cd flutter_web
flutter pub get
flutter run -d chrome
```

## Running Tests

```bash
# From the project root, with venv activated:
python -m pytest backend/tests/ -v
```

**259 tests** across 8 test modules:

| Module | Count | Coverage |
|--------|-------|----------|
| `test_schema.py` | 34 | Schema validation, field types, visibility references |
| `test_visibility.py` | 56 | All 7 condition operators, AND logic, date comparisons |
| `test_form_state.py` | 49 | State management, answer CRUD, cascading visibility |
| `test_actions.py` | 25 | Action builders, model serialization |
| `test_orchestrator.py` | 20 | Orchestrator with mock LLM, intent routing |
| `test_api.py` | 21 | API endpoint integration, session store |
| `test_e2e.py` | 12 | Full multi-turn conversation flows |
| `test_boundary.py` | 24 | Edge cases: 50+ fields, nested deps, date boundaries |
| `test_llm_resilience.py` | 11 | Malformed JSON, retries, LLM exceptions |
| `test_api_e2e.py` | 7 | Multi-turn HTTP API conversations |

## Supported LLM Providers

| Provider | Environment Variables |
|----------|----------------------|
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL_NAME` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME` |
| watsonx | `WATSONX_API_KEY`, `WATSONX_URL`, `WATSONX_PROJECT_ID`, `WATSONX_MODEL_ID` |
| Custom (OpenAI-compatible) | `CUSTOM_LLM_API_ENDPOINT`, `CUSTOM_LLM_API_KEY`, `CUSTOM_LLM_MODEL_NAME` |

### Custom Provider

The `custom` provider supports any LLM endpoint that follows the OpenAI Chat Completions API format. This includes company-hosted platforms like **GOSI Brain**. Set `LLM_PROVIDER=custom` and configure the endpoint, API key, and model name. Under the hood, it uses LangChain's `ChatOpenAI` with a custom `base_url`.

## Form Schema

Forms are defined as JSON schemas. The schema is the single source of truth for all field definitions, validation rules, and visibility conditions. See `backend/schemas/` for examples.

### Supported Field Types

| Type | Description | Requires `options` |
|------|-------------|-------------------|
| `dropdown` | Single-select dropdown | Yes |
| `checkbox` | Multi-select checkboxes | Yes |
| `text` | Free text input | No |
| `date` | Date picker (ISO 8601) | No |
| `datetime` | Date + time picker | No |
| `location` | Lat/lng location picker | No |

### Visibility Conditions

Fields can be conditionally visible based on other fields' values. Conditions use `visible_if` with AND logic (`all` list). Supported operators:

| Operator | Description |
|----------|-------------|
| `EXISTS` | Field has a value |
| `EQUALS` | Field equals a static `value` or another field's value (`value_field`) |
| `NOT_EQUALS` | Field does not equal the comparison |
| `AFTER` | Date is after the comparison date |
| `BEFORE` | Date is before the comparison date |
| `ON_OR_AFTER` | Date is on or after the comparison |
| `ON_OR_BEFORE` | Date is on or before the comparison |

### Validation

Schema validation is handled by Pydantic models in `backend/core/schema.py`. The validator enforces:
- Field IDs must be unique
- `visible_if` conditions must reference existing fields
- `dropdown`/`checkbox` fields must have `options`
- Fields cannot reference themselves in visibility conditions

## API Endpoints

The backend exposes a REST API at `/api`. Start the server with:

```bash
uvicorn backend.api.app:app --reload
```

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Process a user message in a form-filling conversation |
| POST | `/api/validate-schema` | Validate a form schema JSON |
| GET | `/api/schemas` | List available example schemas |
| GET | `/api/schemas/{filename}` | Get a specific example schema |
| POST | `/api/sessions/reset` | Reset/delete a conversation session |
| GET | `/api/health` | Health check |

### POST /api/chat

```json
// Request
{
  "form_schema": { "form_id": "...", "fields": [...] },
  "user_message": "I want annual leave",
  "conversation_id": "optional-uuid"
}

// Response
{
  "action": { "action": "ASK_DATE", "field_id": "start_date", ... },
  "conversation_id": "uuid",
  "answers": { "leave_type": "Annual" }
}
```

### POST /api/validate-schema

```json
// Request
{ "form_schema": { "form_id": "...", "fields": [...] } }

// Response
{ "valid": true, "errors": [] }
```

## Flutter Web App

The Flutter web app provides a three-panel simulation interface:

| Panel | Purpose |
|-------|---------|
| **Chat Panel** (left) | Conversational message list with text input |
| **Widget Panel** (center) | Renders dynamic UI widgets from AI actions (dropdowns, date pickers, checkboxes, etc.) |
| **Debug Panel** (right) | Real-time view of answers, last action JSON, and field visibility status |

Features:
- Schema selector — choose from example schemas or paste custom JSON
- Backend health indicator — shows connection status
- Responsive layout — tabs on narrow screens, side-by-side on wide screens
- Reset conversation, view raw schema JSON

## Development Status

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Project Setup & Environment | Done |
| 1 | Form Schema Definition & Validation | Done |
| 2 | Deterministic Visibility Evaluator | Done |
| 3 | Form State Manager | Done |
| 4 | AI Action Protocol | Done |
| 5 | LangChain Structured Chat Agent | Done |
| 6 | Backend API Layer | Done |
| 7 | Flutter Web App (Simulation & Testing) | Done |
| 8 | Testing & Quality Assurance | Done |
| 9 | Documentation & Deployment | Pending |

# FormPilot AI

GenAI-powered conversational form filling system. An AI agent guides users through complex forms via chat, following structured schemas and deterministic business logic.

## Overview

FormPilot AI helps users fill complex forms through natural conversation. The AI:
- Greets the user and asks them to describe all their form data at once
- Extracts all possible field values from the free-text description (bulk extraction)
- Only asks about remaining missing fields one at a time
- Never assumes or fabricates values — only extracts what the user explicitly stated
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
├── docs/                     # Project documentation
│   ├── schema_guide.md       # How to write a form schema
│   ├── api_reference.md      # Backend API endpoints and contracts
│   └── action_protocol.md    # AI action types and JSON formats
├── Dockerfile                # Backend Docker image
├── docker-compose.yml        # Local development with Docker
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

**285 tests** across 9 test modules:

| Module | Count | Coverage |
|--------|-------|----------|
| `test_schema.py` | 34 | Schema validation, field types, visibility references |
| `test_visibility.py` | 56 | All 7 condition operators, AND logic, date comparisons |
| `test_form_state.py` | 55 | State management, answer CRUD, cascading visibility, bulk answers |
| `test_actions.py` | 25 | Action builders, model serialization |
| `test_orchestrator.py` | 27 | Orchestrator with mock LLM, two-phase flow, multi_answer intent |
| `test_api.py` | 21 | API endpoint integration, session store |
| `test_e2e.py` | 13 | Full multi-turn conversation flows with extraction |
| `test_boundary.py` | 24 | Edge cases: 50+ fields, nested deps, date boundaries |
| `test_llm_resilience.py` | 15 | Malformed JSON, retries, LLM exceptions (extraction + one-at-a-time) |
| `test_api_e2e.py` | 7 | Multi-turn HTTP API conversations |
| `test_bulk_extraction.py` | 9 | Bulk extraction scenarios: complete, partial, gibberish, conditional |

## Documentation

| Document | Description |
|----------|-------------|
| [Schema Guide](docs/schema_guide.md) | How to write a form schema |
| [API Reference](docs/api_reference.md) | Backend API endpoints and contracts |
| [Action Protocol](docs/action_protocol.md) | AI action types and JSON formats |

## Conversation Flow

FormPilot AI uses a **two-phase conversation flow**:

**Phase 1 — Bulk Extraction:**
1. AI greets the user with a MESSAGE action
2. User provides a free-text description of all their form data
3. LLM extracts all possible field values in one pass (`multi_answer` intent)
4. Valid answers are stored; invalid values are silently skipped

**Phase 2 — One-at-a-Time Follow-Up:**
5. For remaining missing required fields, AI asks one field at a time (ASK_* actions)
6. User answers each field individually
7. Repeat until all required fields are complete → FORM_COMPLETE

This approach minimizes back-and-forth by capturing as much data as possible from the initial message, then only asking about what's still missing.

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

## Docker

### Build and run with Docker Compose (development)

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your LLM credentials

# Start the backend
docker compose up --build
```

The backend is available at `http://localhost:8000`.

### Build the Docker image manually

```bash
docker build -t formpilot-ai .
docker run -p 8000:8000 --env-file .env formpilot-ai
```

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
| 9 | Documentation & Deployment | Done |

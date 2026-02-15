# FormPilot AI

GenAI-powered conversational form filling system. An AI agent guides users through complex forms via natural chat, interpreting markdown form definitions and returning structured UI actions.

## Overview

FormPilot AI helps users fill complex forms through natural conversation. The AI:
- Greets the user and asks them to describe all their form data at once
- Extracts all possible field values from the free-text description (bulk extraction)
- Only asks about remaining missing fields one at a time
- Supports tool calls — the AI can request data lookups (e.g. employee lists, injury types) from the frontend
- Never assumes or fabricates values — only extracts what the user explicitly stated
- Returns structured JSON actions to the UI
- Produces a final JSON payload for review and submission

## Architecture

```
┌──────────────────────┐     ┌──────────────────────┐     ┌─────────┐
│  Flutter Web App     │────▶│  Python Backend       │────▶│  LLM    │
│  (Simulation & Test) │◀────│  (FastAPI)            │◀────│  (API)  │
└──────────────────────┘     └──────────────────────┘     └─────────┘
        │                            │
   Chat Panel              Markdown Form Interpretation
   Inline Action Widgets   Conversation Orchestrator
   Mock Tool Execution     System Prompt Builder
   JSON Debug Panel        LLM Resilience Layer
```

### Components

| Component | Purpose |
|-----------|---------|
| **Flutter Web App** | Simulation UI with chat, inline action widgets, mock tool execution, and debug panel |
| **Python Backend** | LangChain agent, markdown-driven orchestrator, API |
| **LLM** | Reasoning, form interpretation, and structured output (no direct tool calling, no API access) |

### Form Definition: Markdown-Driven

Forms are defined as **markdown documents** (`.md` files). The LLM interprets the markdown directly to understand fields, rules, validation, and available tool calls. This replaces the previous JSON schema approach, giving maximum flexibility.

Example markdown forms are in `backend/schemas/`. The markdown includes:
- Field definitions with types and constraints
- Validation rules and dependencies
- Tool call definitions (e.g. `get_establishments`, `get_injury_types`)
- Business rules and conditional logic

### Tool Call Round-Trip

The AI can request tool calls from the frontend (e.g. to fetch dropdown options from an API). The flow is:

1. AI returns a `TOOL_CALL` action with `tool_name` and `tool_args`
2. Frontend executes the tool (real API call or mock in demo)
3. Frontend sends `tool_results` back to the AI in the next request
4. AI uses the results to continue the conversation

## Project Structure

```
form_pilot_ai/
├── backend/                  # Python backend
│   ├── core/                 # Core logic (actions, sessions)
│   ├── agent/                # LangChain agent, orchestrator, prompts
│   ├── api/                  # FastAPI routes
│   ├── schemas/              # Example form definition markdown files
│   └── tests/                # Unit and integration tests
├── flutter_web/              # Flutter web app (simulation & testing)
│   └── lib/
│       ├── models/           # Dart data models (AIAction, ChatResponse)
│       ├── screens/          # Simulation screen (two-panel layout)
│       ├── services/         # ChatService, MockTools
│       └── widgets/          # Chat panel, dynamic widgets, debug panel, schema selector
├── docs/                     # Project documentation
│   ├── schema_guide.md       # How to write a form definition
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
- An LLM API key (OpenAI, Azure OpenAI, watsonx, or any OpenAI-compatible endpoint)

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

**242 tests** across 11 test modules:

| Module | Count | Coverage |
|--------|-------|----------|
| `test_schema.py` | 34 | Schema validation, field types, visibility references |
| `test_visibility.py` | 56 | All 7 condition operators, AND logic, date comparisons |
| `test_form_state.py` | 55 | State management, answer CRUD, cascading visibility, bulk answers |
| `test_actions.py` | 6 | Action builders (message, completion, tool call) |
| `test_orchestrator.py` | 16 | Orchestrator with mock LLM, two-phase flow, tool calls |
| `test_api.py` | 13 | API endpoint integration, session store |
| `test_e2e.py` | 10 | Full multi-turn conversation flows with extraction and tool calls |
| `test_boundary.py` | 24 | Edge cases: 50+ fields, nested deps, date boundaries |
| `test_llm_resilience.py` | 11 | Malformed JSON, retries, LLM exceptions |
| `test_api_e2e.py` | 8 | Multi-turn HTTP API conversations with tool call round-trips |
| `test_bulk_extraction.py` | 5 | Bulk extraction scenarios: complete, partial, gibberish |

## Documentation

| Document | Description |
|----------|-------------|
| [Schema Guide](docs/schema_guide.md) | How to write a form definition (markdown) |
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
5. For remaining missing fields, AI asks one field at a time (ASK_* actions)
6. AI may issue TOOL_CALL actions to fetch data (e.g. dropdown options)
7. User answers each field individually
8. Repeat until all required fields are complete -> FORM_COMPLETE

This approach minimizes back-and-forth by capturing as much data as possible from the initial message, then only asking about what's still missing.

## Action Types

| Action | Description |
|--------|-------------|
| `MESSAGE` | Plain text message to the user |
| `ASK_TEXT` | Request free text input |
| `ASK_DROPDOWN` | Request selection from a list of options |
| `ASK_CHECKBOX` | Request multi-select from a list of options |
| `ASK_DATE` | Request a date value |
| `ASK_DATETIME` | Request a date and time value |
| `ASK_LOCATION` | Request a geographic location |
| `TOOL_CALL` | Request frontend to execute a tool (e.g. data lookup) |
| `FORM_COMPLETE` | All fields collected; final data payload for review |

## Supported LLM Providers

| Provider | Environment Variables |
|----------|----------------------|
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL_NAME` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME` |
| watsonx | `WATSONX_API_KEY`, `WATSONX_URL`, `WATSONX_PROJECT_ID`, `WATSONX_MODEL_ID` |
| Custom (OpenAI-compatible) | `CUSTOM_LLM_API_ENDPOINT`, `CUSTOM_LLM_API_KEY`, `CUSTOM_LLM_MODEL_NAME` |

### Custom Provider

The `custom` provider supports any LLM endpoint that follows the OpenAI Chat Completions API format. This includes:
- Company-hosted platforms like **GOSI Brain**
- Local models via **Ollama** (e.g. `http://localhost:11434/v1/chat/completions`)
- Any OpenAI-compatible endpoint

Set `LLM_PROVIDER=custom` and configure the endpoint, API key, and model name. Under the hood, it uses LangChain's `ChatOpenAI` with a custom `base_url`.

## API Endpoints

The backend exposes a REST API at `/api`. Start the server with:

```bash
uvicorn backend.api.app:app --reload
```

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Process a user message in a form-filling conversation |
| GET | `/api/schemas` | List available example form definitions (markdown) |
| GET | `/api/schemas/{filename}` | Get a specific form definition markdown content |
| POST | `/api/sessions/reset` | Reset/delete a conversation session |
| GET | `/api/health` | Health check |

### POST /api/chat

```json
// Request
{
  "form_context_md": "# Report Injury\n\n## Fields\n...",
  "user_message": "I got injured at work yesterday",
  "conversation_id": "optional-uuid",
  "tool_results": [{"tool_name": "get_establishments", "result": {...}}]
}

// Response
{
  "action": { "action": "ASK_DROPDOWN", "field_id": "establishment", ... },
  "conversation_id": "uuid",
  "answers": { "injury_date": "2025-01-15" }
}
```

## Flutter Web App

The Flutter web app provides a two-panel simulation interface:

| Panel | Purpose |
|-------|---------|
| **Chat Panel** (left) | Conversational messages with inline action widgets (dropdowns, date pickers, etc.) |
| **Debug Panel** (right) | Real-time view of answers, last action JSON, and session info |

Features:
- Form selector — choose from example markdown forms or paste custom markdown
- Inline action widgets — dropdowns, date pickers, checkboxes rendered directly in chat
- Mock tool execution — simulates backend tool calls with realistic test data
- Backend health indicator — shows connection status
- Responsive layout — tabs on narrow screens, side-by-side on wide screens
- Reset conversation, view raw form markdown

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
| 10 | Markdown-Driven Architecture | Done |

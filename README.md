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
│  (Simulation & Test) │◀────│  (FastAPI + LangGraph)│◀────│  (API)  │
└──────────────────────┘     └──────────────────────┘     └─────────┘
        │                            │
   Chat Panel              LangGraph State Machine
   Inline Action Widgets   Node-based Conversation Flow
   Mock Tool Execution     System Prompt Builder
   JSON Debug Panel        LLM Resilience Layer
```

### Components

| Component | Purpose |
|-----------|---------|
| **Flutter Web App** | Simulation UI with chat, inline action widgets, mock tool execution, and debug panel |
| **Python Backend** | LangGraph state machine with explicit nodes and edges, FastAPI API |
| **LLM** | Reasoning, form interpretation, and structured output (no direct tool calling, no API access) |

### LangGraph State Machine

The conversation flow is modeled as an explicit state machine using LangGraph:

```
START -> route_input -> {greeting, tool_handler, validate_input, extraction, conversation}
  greeting      -> END
  tool_handler  -> conversation -> finalize -> END
  validate      -> conversation -> finalize -> END
  extraction    -> {conversation | finalize} -> END
  conversation  -> finalize -> END
```

| Node | Responsibility |
|------|----------------|
| **greeting** | Builds the initial welcome message |
| **tool_handler** | Processes tool results from the frontend into conversation history |
| **validate_input** | Validates user answers (format for dates, LLM context for text) |
| **extraction** | Bulk-extracts field values from the user's free-text description |
| **conversation** | Builds the system prompt, calls the LLM, handles retries |
| **finalize** | Tracks pending fields, resolves text validation, records history |

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
│   │   ├── actions.py        # Action builders (MESSAGE, FORM_COMPLETE, TOOL_CALL)
│   │   └── session.py        # In-memory session store
│   ├── agent/                # LangGraph state machine
│   │   ├── graph.py          # Graph definition (nodes + edges + compile)
│   │   ├── state.py          # FormPilotState TypedDict with reducers
│   │   ├── utils.py          # Shared utilities (validation, JSON, LLM retry)
│   │   ├── nodes/            # Individual graph nodes
│   │   │   ├── greeting.py   # Initial welcome message
│   │   │   ├── extraction.py # Bulk field extraction
│   │   │   ├── validation.py # User answer validation
│   │   │   ├── tool_handler.py # Tool result processing
│   │   │   ├── conversation.py # LLM conversation turn
│   │   │   └── finalize.py   # Action post-processing
│   │   ├── prompts.py        # System prompt templates
│   │   └── llm_provider.py   # LLM factory (OpenAI-compatible)
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
│   ├── api_reference.md      # Backend API endpoints and contracts
│   └── action_protocol.md    # AI action types and JSON formats
├── Dockerfile                # Backend Docker image
├── docker-compose.yml        # Local development with Docker
└── .env.example              # Environment variable template
```

## Setup

### Prerequisites

- Python 3.12+
- Flutter SDK (web enabled)
- An OpenAI-compatible LLM endpoint (e.g. GOSI Brain, Ollama, vLLM, or any OpenAI-compatible API)

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

**75 tests** across 7 test modules:

| Module | Count | Coverage |
|--------|-------|----------|
| `test_orchestrator.py` | 21 | LangGraph with mock LLM, two-phase flow, tool calls |
| `test_api.py` | 16 | API endpoint integration, session store |
| `test_llm_resilience.py` | 12 | Malformed JSON, retries, LLM exceptions |
| `test_actions.py` | 9 | Action builders (message, completion, tool call) |
| `test_e2e.py` | 6 | Full multi-turn conversation flows with extraction and tool calls |
| `test_api_e2e.py` | 6 | Multi-turn HTTP API conversations with tool call round-trips |
| `test_bulk_extraction.py` | 5 | Bulk extraction scenarios: complete, partial, gibberish |

## Documentation

| Document | Description |
|----------|-------------|
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

## LLM Configuration

FormPilot AI works with any **OpenAI-compatible** chat completions endpoint. This includes:
- Company-hosted platforms like **GOSI Brain**
- Local models via **Ollama** (e.g. `http://localhost:11434/v1/chat/completions`)
- **vLLM**, **LiteLLM**, or any OpenAI-compatible API

| Environment Variable | Description |
|----------------------|-------------|
| `CUSTOM_LLM_API_ENDPOINT` | Full URL of the chat completions endpoint |
| `CUSTOM_LLM_API_KEY` | API key / bearer token |
| `CUSTOM_LLM_MODEL_NAME` | Model identifier (defaults to `"default"`) |

Under the hood, it uses LangChain's `ChatOpenAI` with a custom `base_url`, orchestrated by a LangGraph state machine.

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
| 1 | Project Setup & Environment | Done |
| 2 | AI Action Protocol | Done |
| 3 | LangGraph State Machine | Done |
| 4 | Backend API Layer (FastAPI) | Done |
| 5 | Markdown-Driven Form Definitions | Done |
| 6 | Flutter Web App (Simulation & Testing) | Done |
| 7 | Testing & Quality Assurance | Done |
| 8 | Documentation & Deployment | Done |

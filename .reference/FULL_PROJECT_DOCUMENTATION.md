# FormPilot AI - Complete Project Documentation

> **Internal Reference Document**
> Last updated: February 17, 2026
> This file is a deep-dive reference covering every aspect of the FormPilot AI project.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Complete File Structure](#3-complete-file-structure)
4. [Backend Deep Dive](#4-backend-deep-dive)
   - 4.1 [LangGraph State Machine](#41-langgraph-state-machine)
   - 4.2 [Graph Nodes](#42-graph-nodes)
   - 4.3 [State Definition](#43-state-definition)
   - 4.4 [Prompt Engineering](#44-prompt-engineering)
   - 4.5 [Utilities & Guards](#45-utilities--guards)
   - 4.6 [LLM Provider](#46-llm-provider)
   - 4.7 [API Layer](#47-api-layer)
   - 4.8 [Session Management](#48-session-management)
   - 4.9 [Core Modules](#49-core-modules)
5. [Flutter Web App](#5-flutter-web-app)
6. [Form Definitions (Markdown-Driven)](#6-form-definitions-markdown-driven)
7. [AI Action Protocol](#7-ai-action-protocol)
8. [Conversation Flow](#8-conversation-flow)
9. [Tool Call Round-Trip](#9-tool-call-round-trip)
10. [Validation Strategy](#10-validation-strategy)
11. [Testing](#11-testing)
12. [Deployment](#12-deployment)
13. [Configuration](#13-configuration)
14. [Data Flow Diagrams](#14-data-flow-diagrams)
15. [Key Design Decisions](#15-key-design-decisions)

---

## 1. Project Overview

**FormPilot AI** is a GenAI-powered conversational form-filling system. Instead of presenting users with traditional form UIs, an AI chat agent guides them through complex multi-step forms via natural conversation.

### What It Does

1. The user opens a form (defined as a markdown document).
2. The AI greets the user and explains what information is needed.
3. The user can describe all their data in one message (free text).
4. The AI extracts as many field values as possible from that description.
5. For missing fields, the AI asks one at a time using structured UI widgets (dropdowns, date pickers, text inputs, etc.).
6. When the AI needs external data (e.g., a list of establishments), it issues a TOOL_CALL to the frontend, which executes the call and returns results.
7. Once all required fields are collected, the AI returns a FORM_COMPLETE action with the final data payload.

### Core Principles

- **No RAG, no embeddings, no vector databases** - Pure structured form schema + LLM reasoning.
- **Markdown-driven** - Forms are defined as markdown files, not rigid JSON schemas.
- **Deterministic where possible** - Visibility rules, date validation, and answer storage are handled in code, not by the LLM.
- **LLM for conversation only** - The LLM interprets context, generates questions, and validates text relevance. It does NOT call APIs or access databases.
- **Simplicity first** - No microservices, no message queues, no over-engineering.

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend Framework | FastAPI (Python 3.12+) |
| State Machine | LangGraph (from LangChain) |
| LLM Integration | LangChain's ChatOpenAI (OpenAI-compatible endpoint) |
| Data Validation | Pydantic v2 |
| Date Parsing | python-dateutil |
| Frontend | Flutter Web (Dart) |
| Testing | pytest + pytest-asyncio + httpx |
| Containerization | Docker + Docker Compose |

---

## 2. Architecture

### High-Level Architecture Diagram

```
                                     ┌───────────────────────────────┐
                                     │       LLM Service             │
                                     │  (Any OpenAI-compatible API)  │
                                     │  e.g. GOSI Brain, Ollama,     │
                                     │       vLLM, LiteLLM           │
                                     └───────────┬───────────────────┘
                                                 │ HTTP (chat/completions)
                                                 │
┌──────────────────────┐   HTTP/REST   ┌─────────┴─────────────────────┐
│                      │──────────────▶│                                │
│  Flutter Web App     │               │    Python Backend (FastAPI)    │
│  (Chat UI + Widgets) │◀──────────────│                                │
│                      │   JSON        │  ┌──────────────────────────┐  │
│  - Chat Panel        │               │  │  LangGraph State Machine │  │
│  - Inline Widgets    │               │  │                          │  │
│  - Mock Tool Exec    │               │  │  greeting ──▶ END        │  │
│  - Debug Panel       │               │  │  extraction ──▶ conv     │  │
│  - Schema Selector   │               │  │  validation ──▶ conv     │  │
│                      │               │  │  tool_handler ──▶ conv   │  │
└──────────────────────┘               │  │  conversation ──▶ final  │  │
                                       │  └──────────────────────────┘  │
                                       │                                │
                                       │  ┌──────────────────────────┐  │
                                       │  │  Session Store (in-mem)  │  │
                                       │  │  Prompt Builder          │  │
                                       │  │  Answer Validation       │  │
                                       │  └──────────────────────────┘  │
                                       └────────────────────────────────┘
```

### Communication Flow

```
User ──▶ Flutter App ──▶ POST /api/chat ──▶ LangGraph ──▶ LLM ──▶ JSON Action
                                                                        │
User ◀── Flutter App ◀── ChatResponse ◀── Graph Result ◀────────────────┘
```

### Key Architectural Rules

1. **The LLM never calls APIs** - It only reasons about form fields and generates JSON actions.
2. **The Flutter app handles all external calls** - When the AI needs data (e.g., dropdown options from an API), it returns a TOOL_CALL action. The Flutter app executes it and sends results back.
3. **All visibility logic is deterministic** - Field visibility conditions are evaluated in Python code, never by the LLM.
4. **State lives in the backend** - The LangGraph state machine maintains all conversation state server-side. The Flutter app is stateless (aside from UI state).

---

## 3. Complete File Structure

```
form_pilot_ai/
│
├── .cursor/                              # Cursor IDE configuration
│   └── rules/
│       └── Cursor_Implementation_Rules_GenAI_Form_System_v2.mdc
│
├── .docs/                                # Additional technical docs
│   └── custom_llm_api.md                 # Custom LLM API reference
│
├── .reference/                           # Internal reference docs
│   └── FULL_PROJECT_DOCUMENTATION.md     # THIS FILE
│
├── docs/                                 # Public documentation
│   ├── api_reference.md                  # REST API endpoint docs
│   └── action_protocol.md               # AI action types & JSON formats
│
├── backend/                              # Python backend (FastAPI + LangGraph)
│   │
│   ├── agent/                            # LangGraph state machine
│   │   ├── __init__.py
│   │   ├── graph.py                      # Graph definition, compilation, state helpers
│   │   ├── state.py                      # FormPilotState TypedDict with reducers
│   │   ├── prompts.py                    # System prompt templates & builders
│   │   ├── utils.py                      # JSON extraction, validation, LLM retry
│   │   ├── llm_provider.py              # LLM factory (OpenAI-compatible)
│   │   └── nodes/                        # Individual graph nodes
│   │       ├── __init__.py               # Node exports
│   │       ├── greeting.py               # Welcome message builder
│   │       ├── extraction.py             # Bulk field extraction from free text
│   │       ├── validation.py             # User answer validation (format + context)
│   │       ├── tool_handler.py           # Tool result processing
│   │       ├── conversation.py           # LLM conversation turn
│   │       └── finalize.py               # Action post-processing & state tracking
│   │
│   ├── api/                              # FastAPI REST API
│   │   ├── app.py                        # Application factory, middleware, startup
│   │   └── routes.py                     # Endpoint definitions
│   │
│   ├── core/                             # Core business logic
│   │   ├── actions.py                    # Action builder functions
│   │   └── session.py                    # In-memory session store
│   │
│   ├── schemas/                          # Example form definitions
│   │   └── form_pilot_report_injury.md   # Occupational Injury Report (main form)
│   │
│   ├── tests/                            # Test suite (73 tests)
│   │   ├── conftest.py                   # Fixtures (GraphRunner helper)
│   │   ├── test_actions.py              # Action builders (6 tests)
│   │   ├── test_orchestrator.py         # LangGraph with mock LLM (16 tests)
│   │   ├── test_api.py                  # API endpoints (13 tests)
│   │   ├── test_e2e.py                  # End-to-end conversations (10 tests)
│   │   ├── test_llm_resilience.py       # LLM failure handling (11 tests)
│   │   ├── test_api_e2e.py             # API-level E2E (8 tests)
│   │   └── test_bulk_extraction.py     # Bulk extraction (5 tests)
│   │
│   ├── pyproject.toml                    # Python project config (pytest, ruff)
│   └── requirements.txt                  # Python dependencies
│
├── flutter_web/                          # Flutter web app
│   ├── lib/
│   │   ├── main.dart                     # App entry point
│   │   ├── models/
│   │   │   ├── form_schema.dart          # Dart form schema models
│   │   │   └── ai_action.dart            # Dart AI action models
│   │   ├── screens/
│   │   │   └── simulation_screen.dart    # Two-panel simulation screen
│   │   ├── services/
│   │   │   ├── chat_service.dart         # Backend HTTP client
│   │   │   └── mock_tools.dart           # Mock tool execution for testing
│   │   └── widgets/
│   │       ├── chat_panel.dart           # Chat UI with inline widgets
│   │       ├── debug_panel.dart          # JSON debug/inspector panel
│   │       ├── dynamic_widget_panel.dart # Dynamic widget renderer
│   │       └── schema_selector.dart      # Form selector dropdown
│   ├── web/
│   │   └── manifest.json
│   ├── pubspec.yaml                      # Flutter dependencies
│   ├── analysis_options.yaml
│   └── README.md
│
├── Dockerfile                            # Multi-stage Docker build
├── docker-compose.yml                    # Docker Compose for local dev
├── .env.example                          # Environment variable template
├── .gitignore
└── README.md                             # Main project README
```

---

## 4. Backend Deep Dive

### 4.1 LangGraph State Machine

The heart of the system is a **LangGraph StateGraph** defined in `backend/agent/graph.py`. It models the conversation as an explicit, inspectable state machine with 6 nodes and conditional edges.

#### Graph Topology

```
                         ┌──────────────────────────────────────┐
                         │              START                    │
                         └───────────────┬──────────────────────┘
                                         │
                                    route_input()
                           ┌────────┬────┴────┬────────┬────────┐
                           │        │         │        │        │
                           ▼        ▼         ▼        ▼        ▼
                       greeting  tool_     validate  extract  conver-
                                handler    _input    -ion     sation
                           │        │         │        │        │
                           │        │         │        │        │
                           ▼        ▼         ▼        │        │
                          END    conver-   conver-     │        │
                                 sation    sation      │        │
                                    │         │        │        │
                                    └────┬────┘   route_after   │
                                         │       extraction()   │
                                         │        ┌──┴──┐       │
                                         │        │     │       │
                                         ▼        ▼     ▼       │
                                      finalize ◀──┘  conver- ◀──┘
                                         │       sation
                                         │         │
                                         │    route_after
                                         │    conversation()
                                         │      ┌──┴──┐
                                         │      │     │
                                         ▼      ▼     ▼
                                        END  finalize END
                                               │   (LLM failed)
                                               ▼
                                              END
```

#### Routing Logic (`route_input`)

The entry router decides which node to enter based on the current state:

| Priority | Condition | Route To |
|----------|-----------|----------|
| 1 | No history + empty message | `greeting` |
| 2 | `tool_results` present | `tool_handler` |
| 3 | `pending_field_id` + user message | `validate_input` |
| 4 | First real message, no extraction yet | `extraction` |
| 5 | Default | `conversation` |

#### How the Graph Executes

1. **Compile once** at startup: `compile_graph()` builds and compiles the graph.
2. **Per request**: The API prepares a turn state with `prepare_turn_input()`, then calls `await graph.ainvoke(turn_state)`.
3. **Result**: The graph traverses nodes based on routing, each node returns partial state updates, and the final state contains the `action` dict to return to the client.

### 4.2 Graph Nodes

Each node is a focused function in `backend/agent/nodes/` that takes `FormPilotState` and returns a partial state update dict.

#### Node: `greeting` (greeting.py)

**Purpose**: Generates the initial welcome message when a new conversation starts.

**What it does**:
1. Extracts the form title from the markdown's first `# ` heading.
2. Summarizes required fields into a natural-language sentence (e.g., "I'll walk you through about 15 items - things like your establishment, occupation, a few important dates...").
3. Returns a `MESSAGE` action with the greeting text.

**Input**: `form_context_md`
**Output**: `action` (MESSAGE), `conversation_history` (assistant greeting)

---

#### Node: `extraction` (extraction.py)

**Purpose**: Bulk-extracts field values from the user's initial free-text description.

**What it does**:
1. Builds an extraction-specific system prompt (different from the conversation prompt).
2. Sends the user's message + extraction prompt to the LLM.
3. Expects a `{"intent": "multi_answer", "answers": {"fieldId": "value"}, "message": "..."}` response.
4. Validates extracted date/datetime values before storing.
5. If the LLM returns a direct action instead (e.g., TOOL_CALL), routes to finalize.

**Input**: `form_context_md`, `user_message`, `llm`, `field_types`
**Output**: `answers` (extracted values), `initial_extraction_done` = true, `parsed_llm_response` (if direct action)

---

#### Node: `validate_input` (validation.py)

**Purpose**: Validates the user's answer for the currently pending field.

**Two validation strategies**:

| Strategy | Applies To | How It Works |
|----------|-----------|--------------|
| **Format validation** | `ASK_DATE`, `ASK_DATETIME` | Deterministic check using `python-dateutil`. If invalid, injects a system message directing the LLM to re-ask. |
| **Context validation** | `ASK_TEXT` | Holds the answer without storing it. Injects a system message asking the LLM to judge if the answer is relevant. If the LLM moves to the next field, the answer is accepted (stored by finalize). If the LLM re-asks the same field, the answer is discarded. |

**Input**: `user_message`, `pending_field_id`, `pending_action_type`
**Output**: `answers` (if format-valid), `pending_text_value`/`pending_text_field_id` (if text), `conversation_history`

---

#### Node: `tool_handler` (tool_handler.py)

**Purpose**: Processes tool results returned from the frontend.

**What it does**:
1. Iterates over each tool result in `tool_results`.
2. Extracts human-readable option names from the result data (looks for common patterns like `name.english`, `value.english`, `label`, etc.).
3. Adds the tool result as a conversation history entry with an instruction directive telling the LLM how to use the data.
4. Clears the `pending_tool_name` state.

**Input**: `tool_results`, `user_message`
**Output**: `conversation_history`, `pending_tool_name` = None

---

#### Node: `conversation` (conversation.py)

**Purpose**: Runs an LLM conversation turn to get the next action.

**What it does**:
1. Builds the system prompt using `build_system_prompt()` with:
   - Condensed form context (key sections only for small models)
   - Current answered fields
   - Next-step hint (explicit directive for what to do next)
2. Converts conversation history to LangChain message objects.
3. Calls `call_llm_with_retry()` which handles retries and guard validations.
4. If the LLM succeeds, sets `parsed_llm_response` for finalize.
5. If the LLM fails completely, sets a fallback MESSAGE action.

**Input**: `form_context_md`, `user_message`, `llm`, `answers`, `conversation_history`, `required_fields`
**Output**: `parsed_llm_response`, `conversation_history`, `user_message_added`

---

#### Node: `finalize` (finalize.py)

**Purpose**: Post-processes the LLM response and tracks conversation state.

**What it does**:
1. **Resolves pending text answers**: If a text answer was being held for LLM validation:
   - If the LLM re-asked the same field -> answer is **rejected** (discarded).
   - If the LLM moved to a different field -> answer is **accepted** (stored).
2. **Stores explicit values**: If the LLM's response includes a `value` for a `field_id`, stores it.
3. **Tracks pending state**: Updates `pending_field_id`, `pending_action_type`, `pending_tool_name` based on the new action type.
4. **Handles FORM_COMPLETE**: Merges all answers into the `data` field.
5. **Records history**: Adds the assistant's message to conversation history.

**Input**: `parsed_llm_response`, `pending_text_value`, `pending_text_field_id`, `answers`
**Output**: `action`, `answers`, `pending_field_id`, `pending_action_type`, `conversation_history`

---

### 4.3 State Definition

Defined in `backend/agent/state.py` as a `TypedDict`:

```python
class FormPilotState(TypedDict, total=False):
    # --- Input (set per request) ---
    form_context_md: str              # The markdown form definition
    user_message: str                 # Current user message
    tool_results: list[dict] | None   # Tool results from frontend
    llm: Any                          # LangChain BaseChatModel instance

    # --- Accumulated (persists across turns, with reducers) ---
    answers: Annotated[dict, merge_answers]           # All collected answers
    conversation_history: Annotated[list[dict], add]  # Full chat history
    required_fields: list[str]        # Required field IDs from form
    field_types: dict[str, str]       # field_id -> type mapping

    # --- Phase tracking ---
    initial_extraction_done: bool     # Whether bulk extraction has run
    pending_field_id: str | None      # Field currently being asked
    pending_action_type: str | None   # ASK_* type of pending field
    pending_text_value: str | None    # Held text answer awaiting LLM validation
    pending_text_field_id: str | None # Field ID of held text answer
    pending_tool_name: str | None     # Tool currently awaiting results

    # --- Output ---
    action: dict                      # The action dict returned to the UI

    # --- Intermediate (ephemeral, reset each turn) ---
    parsed_llm_response: dict | None  # Raw LLM response before finalization
    user_message_added: bool          # Whether user message was added to history
```

#### Reducers

LangGraph uses **reducers** for fields that accumulate across nodes:

| Field | Reducer | Behavior |
|-------|---------|----------|
| `answers` | `merge_answers` | New answers are **merged** into existing dict |
| `conversation_history` | `add` (built-in) | New entries are **appended** to existing list |

This means when a node returns `{"answers": {"injuryDate": "2026-01-15"}}`, it doesn't replace the entire answers dict - it merges into it.

### 4.4 Prompt Engineering

Defined in `backend/agent/prompts.py`. There are two prompt templates:

#### Main Conversation Prompt (`SYSTEM_PROMPT_TEMPLATE`)

This is the primary system prompt for field-by-field conversation. It includes:

1. **Identity**: "You are a JSON-only API called FormPilot AI"
2. **Available actions**: All 9 action types with exact JSON format
3. **Rules**: Ask one field at a time, never re-ask answered fields, never fabricate values, etc.
4. **Context validation examples**: Shows the LLM when to accept/reject text answers
5. **TOOL_CALL examples**: Shows the correct two-step flow (call tool first, then ask with options)
6. **Form reference data**: The condensed markdown form definition
7. **Current state**: Answered fields, next-step hint, missing required fields

#### Extraction Prompt (`EXTRACTION_SYSTEM_PROMPT_TEMPLATE`)

A simpler prompt for bulk extraction from the user's initial free-text:

1. **Task**: Extract field values from the user's message
2. **Rules**: Only extract explicitly stated values, use ISO dates, skip uncertain fields
3. **Expected format**: `{"intent": "multi_answer", "answers": {...}, "message": "..."}`

#### Form Context Condenser

Large markdown files overwhelm small LLMs (3B-8B params). The `condense_form_context()` function:

1. If the markdown is under 150 lines, uses it as-is.
2. Otherwise, extracts only key sections: "Tool Calls", "Form Overview", "Field Summary", "Conditional Logic", "Chat Agent Instructions".
3. Falls back to head (50 lines) + tail (100 lines) if section extraction fails.

#### Next-Step Hint Builder

The `_build_next_step_hint()` function generates an explicit directive for the LLM:

- **No answers yet**: "Check field #1 in the summary table. If it says TOOL_CALL FIRST, return a TOOL_CALL."
- **Some answers**: Lists all answered fields (forbids re-asking), lists missing required fields, names the next field to ask.
- **All required done**: "All required fields are answered. You may return FORM_COMPLETE."

### 4.5 Utilities & Guards

Defined in `backend/agent/utils.py`.

#### JSON Extraction (`extract_json`)

Extracts JSON from LLM output. Handles three cases:
1. Direct JSON parse
2. JSON wrapped in markdown code fences (` ```json ... ``` `)
3. JSON embedded in surrounding text (finds `{...}` boundaries)

#### LLM Guard Validations (inside `call_llm_with_retry`)

After parsing the LLM response, several guards catch common mistakes:

| Guard | What It Catches | What It Does |
|-------|----------------|--------------|
| **Unknown action** | LLM invents an action type like "RESPOND" | Converts to MESSAGE if text exists, otherwise retries |
| **Re-ask answered field** | LLM asks about a field that already has an answer | Retries with "WRONG. Field X is already answered" |
| **MESSAGE during form filling** | LLM uses MESSAGE instead of ASK_* to ask a question | Retries with "Use ASK_TEXT, ASK_DATE, etc." |
| **Empty dropdown options** | LLM returns ASK_DROPDOWN with `options: []` | Retries with "You need to TOOL_CALL first" |
| **Premature FORM_COMPLETE** | LLM says form is complete but required fields are missing | Retries with list of missing fields |

Each retry appends a corrective message to the conversation and re-invokes the LLM (up to 3 retries).

#### Answer Validation

| Validator | Checks |
|-----------|--------|
| `validate_date_answer` | Not empty, contains digits, parseable by dateutil, produces a valid date |
| `validate_datetime_answer` | Same as date but for datetime |
| `validate_answer_for_action` | Dispatcher: calls date/datetime validators for ASK_DATE/ASK_DATETIME, accepts all others |

#### Tool Result Helpers

`extract_options_hint` scans tool result data for option names. It looks for common patterns:
- `name.english` (bilingual objects)
- `name` (simple strings)
- `value.english` (LOV data)
- `label`, `title`, `text`, `description` fields

Returns a JSON array of option strings to help the LLM present them correctly.

### 4.6 LLM Provider

Defined in `backend/agent/llm_provider.py`.

**Factory function**: `get_llm(**kwargs) -> BaseChatModel`

- Reads from environment variables: `CUSTOM_LLM_API_ENDPOINT`, `CUSTOM_LLM_API_KEY`, `CUSTOM_LLM_MODEL_NAME`
- Uses LangChain's `ChatOpenAI` with a custom `base_url`
- Strips `/chat/completions` suffix from the endpoint (ChatOpenAI appends it)
- Defaults: `temperature=0`, `max_tokens=1024`, `request_timeout=300`
- Works with any OpenAI-compatible endpoint (GOSI Brain, Ollama, vLLM, LiteLLM, etc.)

### 4.7 API Layer

#### Application Factory (`backend/api/app.py`)

`create_app()` does the following:

1. Creates a FastAPI app with title, description, version
2. Configures CORS middleware (all origins in development)
3. Initializes the LLM via `get_llm()`
4. Compiles the LangGraph state machine (once, shared across all sessions)
5. Creates a `SessionStore` with configurable timeout
6. Injects dependencies into routes via `configure_routes()`
7. Includes the router with `/api` prefix

#### Endpoints (`backend/api/routes.py`)

| Method | Path | Description | Request | Response |
|--------|------|-------------|---------|----------|
| POST | `/api/chat` | Process a message in a conversation | `ChatRequest` | `ChatResponse` |
| GET | `/api/schemas` | List available form definitions | - | Schema list |
| GET | `/api/schemas/{filename}` | Get a form definition's content | filename path param | Content |
| POST | `/api/sessions/reset` | Delete a conversation session | `ResetRequest` | Success/failure |
| GET | `/api/health` | Health check | - | Status + session count |

#### POST /api/chat - Detailed Flow

```
1. Validate request (form_context_md not empty)
2. Try to resume session by conversation_id
3. If no session found, create new one:
   a. create_initial_state() extracts required_fields and field_types from markdown
   b. Creates a Session object with the initial state
4. prepare_turn_input() sets user_message, tool_results, resets ephemeral fields
5. await graph.ainvoke(turn_state) runs the state machine
6. Persist result_state back to session
7. Return ChatResponse with action, conversation_id, answers
```

### 4.8 Session Management

Defined in `backend/core/session.py`.

#### Session Class

Each `Session` holds:
- `state: FormPilotState` - The LangGraph state dict (persists across turns)
- `created_at: float` - Creation timestamp
- `last_accessed_at: float` - Last access timestamp

#### SessionStore Class

In-memory session storage with:
- `create_session(form_context_md, llm, conversation_id?)` - Creates initial LangGraph state and wraps it in a Session
- `get_session(conversation_id)` - Returns session (None if expired or not found)
- `delete_session(conversation_id)` - Removes a session
- `cleanup_expired()` - Removes all expired sessions
- Default timeout: 30 minutes

**Note**: For production, this should be replaced with Redis or similar persistent storage.

### 4.9 Core Modules

#### Actions (`backend/core/actions.py`)

Simple builder functions for action dicts:

| Function | Returns |
|----------|---------|
| `build_message_action(text)` | `{"action": "MESSAGE", "text": "..."}` |
| `build_completion_payload(answers)` | `{"action": "FORM_COMPLETE", "data": {...}}` |
| `build_tool_call_action(tool_name, tool_args, message)` | `{"action": "TOOL_CALL", ...}` |

---

## 5. Flutter Web App

The Flutter web app is a simulation and testing interface. It does NOT represent the production Flutter integration (which would be embedded in a real mobile app).

### App Structure

| Component | File | Purpose |
|-----------|------|---------|
| Entry point | `main.dart` | Creates `FormPilotApp` with Material3 theme |
| Main screen | `simulation_screen.dart` | Two-panel layout: chat + debug |
| Chat panel | `chat_panel.dart` | Conversational UI with inline action widgets |
| Debug panel | `debug_panel.dart` | Real-time JSON inspector for answers and actions |
| Dynamic widgets | `dynamic_widget_panel.dart` | Renders dropdowns, date pickers, checkboxes inline |
| Schema selector | `schema_selector.dart` | Dropdown to choose form definitions from backend |
| Chat service | `chat_service.dart` | HTTP client for `/api/chat`, `/api/schemas`, etc. |
| Mock tools | `mock_tools.dart` | Simulates tool execution with realistic test data |
| Data models | `ai_action.dart`, `form_schema.dart` | Dart models for actions and schemas |

### How the Flutter App Works

1. User selects a form from the schema selector dropdown.
2. Flutter sends an empty `user_message` to `/api/chat` -> gets greeting.
3. User types a message in the chat panel.
4. Flutter sends the message to `/api/chat` -> gets an action response.
5. Based on the action type:
   - `MESSAGE` -> Shows text bubble
   - `ASK_DROPDOWN` -> Renders an inline dropdown widget
   - `ASK_DATE` -> Renders an inline date picker
   - `ASK_TEXT` -> Shows text input field
   - `TOOL_CALL` -> Executes mock tool, sends results back to `/api/chat`
   - `FORM_COMPLETE` -> Shows final data summary
6. Debug panel shows real-time answers, last action JSON, session info.

### Mock Tool Execution

The `mock_tools.dart` file simulates tool calls with hardcoded test data. For example:
- `get_establishments` returns 2-3 sample establishments with occupations
- `get_injury_types` returns sample injury type options
- `show_location_picker` returns a mock Riyadh location

---

## 6. Form Definitions (Markdown-Driven)

Forms are defined as **markdown documents** that the LLM interprets directly. This is the primary form definition approach (replacing the older JSON schema approach).

### Why Markdown?

- **Maximum flexibility** - Can include complex business rules, conditional logic, tool call instructions, and examples in natural language
- **LLM-native** - LLMs understand markdown naturally; no need for a rigid schema parser
- **Human-readable** - Form authors can write and review definitions easily
- **Extensible** - Add new sections, rules, or instructions without changing backend code

### Markdown Form Structure

A markdown form definition typically contains:

```markdown
# Form Title

## Architecture / Communication Model
(How the AI and Flutter app communicate)

## Form Overview
(Purpose, language, flow steps)

## Step N: Step Name
(Detailed field-by-field specifications)

### N.M - Field Name
| Property | Value |
|----------|-------|
| Field ID | `fieldId` |
| Type     | dropdown/text/date/etc. |
| Required | Yes/No |
| ...      | ... |

## Field Summary Table
| # | Field ID | Type | Required | Before Asking | Ask User |
(Quick reference for all fields)

## Conditional Logic Summary
(Business rules and dependencies)

## Chat Agent Instructions
(Step-by-step flow for the AI)
```

### Key Sections the Backend Parses

The backend extracts structured data from the markdown:

1. **Field Summary Table** -> `extract_required_field_ids()` gets required field IDs
2. **Field Summary Table** -> `extract_field_type_map()` gets field_id -> type mapping
3. **First heading** -> `extract_form_title()` gets the form title
4. **Required fields by type** -> `summarize_required_fields()` generates a natural greeting

### Example: Report Occupational Injury Form

The main form (`form_pilot_report_injury.md`) is a comprehensive 17-field form for reporting work injuries to GOSI (Saudi Arabia's social insurance). It includes:

- 3 sequential steps (Establishment, Injury Details, Emergency Contact)
- 15+ fields across dropdown, date, text, and location types
- Multiple tool calls (get_establishments, get_injury_types, get_injury_reasons, show_location_picker)
- Conditional fields (delay reason only if 7+ day gap)
- Feature flag dependencies
- Bilingual support (Arabic/English)

---

## 7. AI Action Protocol

The AI communicates with the frontend through structured JSON actions. Each action tells the UI what to render.

### Action Types

| Action | UI Widget | When Used | Key Fields |
|--------|-----------|-----------|------------|
| `MESSAGE` | Text bubble | Greeting, summaries, errors | `text` |
| `ASK_DROPDOWN` | Dropdown selector | Fields with predefined options | `field_id`, `label`, `options`, `message` |
| `ASK_CHECKBOX` | Checkbox group | Multi-select fields | `field_id`, `label`, `options`, `message` |
| `ASK_TEXT` | Text input | Free text fields | `field_id`, `label`, `message` |
| `ASK_DATE` | Date picker | Date fields | `field_id`, `label`, `message` |
| `ASK_DATETIME` | Date+time picker | Datetime fields | `field_id`, `label`, `message` |
| `ASK_LOCATION` | Location picker / map | Location fields | `field_id`, `label`, `message` |
| `TOOL_CALL` | Loading indicator | Data lookups, API calls | `tool_name`, `tool_args`, `message` |
| `FORM_COMPLETE` | Summary view | All fields collected | `data`, `message` |

### Action JSON Examples

```json
// Greeting
{"action": "MESSAGE", "text": "Hi! I'll help you fill out the form."}

// Dropdown question
{"action": "ASK_DROPDOWN", "field_id": "selectedEstablishment",
 "label": "Which establishment?", "options": ["Company A", "Company B"],
 "message": "Please select your establishment."}

// Tool call
{"action": "TOOL_CALL", "tool_name": "get_establishments",
 "tool_args": {}, "message": "Looking up your establishments..."}

// Form complete
{"action": "FORM_COMPLETE",
 "data": {"injuryDate": "2026-01-15", "injuryTime": "10:00"},
 "message": "All fields are complete!"}
```

---

## 8. Conversation Flow

### Two-Phase Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PHASE 1: Bulk Extraction                     │
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────┐             │
│  │ User     │    │ AI sends     │    │ User provides │             │
│  │ opens    │───▶│ GREETING     │───▶│ free-text     │             │
│  │ form     │    │ (MESSAGE)    │    │ description   │             │
│  └──────────┘    └──────────────┘    └───────┬───────┘             │
│                                              │                      │
│                                              ▼                      │
│                                 ┌────────────────────────┐          │
│                                 │ LLM extracts all       │          │
│                                 │ possible field values   │          │
│                                 │ (multi_answer intent)   │          │
│                                 └────────────┬───────────┘          │
│                                              │                      │
│                                    ┌─────────┴──────────┐           │
│                                    │                     │           │
│                              All fields           Some fields       │
│                              extracted            still missing     │
│                                    │                     │           │
│                                    ▼                     ▼           │
│                              FORM_COMPLETE       Go to Phase 2      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                   PHASE 2: One-at-a-Time Follow-Up                  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │                    For each missing field:                │       │
│  │                                                          │       │
│  │  Does the field need a TOOL_CALL first?                  │       │
│  │       │                                                  │       │
│  │    ┌──┴──┐                                               │       │
│  │   YES    NO                                              │       │
│  │    │      │                                              │       │
│  │    ▼      ▼                                              │       │
│  │  TOOL_CALL   ASK_* action                                │       │
│  │    │         (dropdown, text, date, etc.)                │       │
│  │    ▼              │                                      │       │
│  │  Frontend         │                                      │       │
│  │  executes tool    │                                      │       │
│  │    │              │                                      │       │
│  │    ▼              │                                      │       │
│  │  Send results     │                                      │       │
│  │  back to AI       │                                      │       │
│  │    │              │                                      │       │
│  │    ▼              ▼                                      │       │
│  │  ASK_* with    User answers                              │       │
│  │  real options      │                                     │       │
│  │    │              │                                      │       │
│  │    ▼              ▼                                      │       │
│  │  User answers   Validate answer                          │       │
│  │    │              │                                      │       │
│  │    └──────┬───────┘                                      │       │
│  │           │                                              │       │
│  │    Store answer, move to next field                      │       │
│  │           │                                              │       │
│  │           ▼                                              │       │
│  │    All required fields answered?                         │       │
│  │    ┌──┴──┐                                               │       │
│  │   NO    YES                                              │       │
│  │    │      │                                              │       │
│  │    ▼      ▼                                              │       │
│  │  Loop    FORM_COMPLETE                                   │       │
│  └──────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
```

### Detailed Per-Turn Sequence

```
Frontend                    Backend API                 LangGraph                   LLM
   │                            │                          │                         │
   │  POST /api/chat            │                          │                         │
   │  {form_context_md,         │                          │                         │
   │   user_message,            │                          │                         │
   │   conversation_id,         │                          │                         │
   │   tool_results}            │                          │                         │
   │──────────────────────────▶│                          │                         │
   │                            │  get/create session      │                         │
   │                            │  prepare_turn_input()    │                         │
   │                            │                          │                         │
   │                            │  await graph.ainvoke()   │                         │
   │                            │────────────────────────▶│                         │
   │                            │                          │  route_input()          │
   │                            │                          │  -> select node         │
   │                            │                          │                         │
   │                            │                          │  node executes          │
   │                            │                          │  (may call LLM)         │
   │                            │                          │─────────────────────────▶
   │                            │                          │                         │
   │                            │                          │◀─────────────────────────
   │                            │                          │  JSON response          │
   │                            │                          │                         │
   │                            │                          │  finalize node          │
   │                            │                          │  (post-process)         │
   │                            │                          │                         │
   │                            │◀────────────────────────│  result_state           │
   │                            │                          │                         │
   │                            │  persist state           │                         │
   │                            │                          │                         │
   │  ChatResponse              │                          │                         │
   │  {action, conversation_id, │                          │                         │
   │   answers}                 │                          │                         │
   │◀──────────────────────────│                          │                         │
```

---

## 9. Tool Call Round-Trip

When the AI needs external data (e.g., dropdown options from an API), it doesn't call the API itself. Instead:

```
Step 1: AI returns TOOL_CALL action
─────────────────────────────────────────────────────
Backend -> Frontend:
{
  "action": {
    "action": "TOOL_CALL",
    "tool_name": "get_establishments",
    "tool_args": {},
    "message": "Looking up your establishments..."
  }
}

Step 2: Frontend executes tool, sends results back
─────────────────────────────────────────────────────
Frontend -> Backend:
{
  "form_context_md": "...",
  "user_message": "",
  "conversation_id": "abc-123",
  "tool_results": [
    {
      "tool_name": "get_establishments",
      "result": {
        "establishments": [
          {"registrationNo": "5001234567",
           "name": {"english": "Riyadh Technology Co."}}
        ]
      }
    }
  ]
}

Step 3: AI uses results to present options
─────────────────────────────────────────────────────
Backend -> Frontend:
{
  "action": {
    "action": "ASK_DROPDOWN",
    "field_id": "selectedEstablishment",
    "label": "Which establishment?",
    "options": ["Riyadh Technology Co."],
    "message": "Which establishment was the injury related to?"
  }
}
```

### Available Tool Calls (Injury Report Form)

| Tool | Purpose | When Called |
|------|---------|------------|
| `get_establishments` | Get user's establishment list | Start of conversation |
| `get_injury_types` | Get injury type options | Before asking injury type |
| `get_injury_reasons(typeName)` | Get reasons for an injury type | After injury type selected |
| `get_country_list` | Get country list | When collecting location data |
| `show_location_picker` | Open native map for location pin | When asking for location |
| `get_required_documents(type)` | Get document upload requirements | After injury submission |
| `set_field_value(fieldId, value)` | Set a form field value | After each user answer |
| `validate_step(stepNumber)` | Check step completion | Before proceeding |
| `submit_injury_report` | Submit injury report | After Step 2 complete |
| `submit_emergency_contact(phone, code)` | Save emergency contact | After phone provided |
| `upload_document(docIndex)` | Trigger file upload | When uploading docs |
| `submit_final` | Final submission | After Step 3 complete |

---

## 10. Validation Strategy

FormPilot AI uses a **dual validation strategy**: deterministic code validation for structured data and LLM-based validation for free text.

### Validation Matrix

| Field Type | Validation | Where | Mechanism |
|-----------|-----------|-------|-----------|
| `ASK_DATE` | Format check | `validate_input` node | `python-dateutil` parsing, rejects non-date strings |
| `ASK_DATETIME` | Format check | `validate_input` node | `python-dateutil` parsing |
| `ASK_TEXT` | Context check | `conversation` node + `finalize` node | LLM judges relevance; answer held until LLM decision |
| `ASK_DROPDOWN` | Implicit (UI) | Frontend | User selects from provided options |
| `ASK_CHECKBOX` | Implicit (UI) | Frontend | User selects from provided options |
| `ASK_LOCATION` | Implicit (UI) | Frontend | Location picked from map |

### Text Validation Flow (Detailed)

```
1. User answers a pending ASK_TEXT field
2. validate_input node:
   - Does NOT store the answer
   - Saves it as pending_text_value / pending_text_field_id
   - Injects a system message: "VALIDATE this answer: Is it relevant?"
3. conversation node:
   - LLM sees the validation request
   - If answer is good: LLM moves to next field (ASK_* for a different field_id)
   - If answer is bad: LLM re-asks same field (ASK_TEXT with same field_id)
4. finalize node:
   - Checks if LLM's action has the same field_id as the pending text
   - If SAME field_id -> answer REJECTED (discarded)
   - If DIFFERENT field_id -> answer ACCEPTED (stored in answers)
```

### Guard Validations (LLM Output)

| Guard | Trigger | Action |
|-------|---------|--------|
| Invalid JSON | LLM returns non-JSON text | Retry with "WRONG. Respond with ONLY JSON." |
| Unknown action type | LLM invents a new action | Convert to MESSAGE or retry |
| Re-ask answered field | LLM asks about a field that already has a value | Retry with "Field X is already answered" |
| MESSAGE during filling | LLM uses MESSAGE instead of ASK_* | Retry with "Use the correct ASK_* action" |
| Empty dropdown options | ASK_DROPDOWN with `options: []` | Retry with "You must TOOL_CALL first" |
| Premature FORM_COMPLETE | All required fields not answered | Retry with list of missing fields |

---

## 11. Testing

### Test Suite Overview

**75 tests** across 7 test files, all using pytest + pytest-asyncio.

| File | Tests | What It Covers |
|------|-------|---------------|
| `test_orchestrator.py` | 21 | LangGraph with mock LLM, two-phase flow, tool call routing |
| `test_api.py` | 16 | FastAPI endpoint integration, session management, CORS |
| `test_llm_resilience.py` | 12 | Malformed JSON recovery, retry mechanism, LLM exceptions, timeout handling |
| `test_actions.py` | 9 | Action builder functions (message, completion, tool_call) |
| `test_e2e.py` | 6 | Full multi-turn conversations (greeting -> extraction -> follow-up -> complete) |
| `test_api_e2e.py` | 6 | HTTP-level multi-turn conversations with tool call round-trips |
| `test_bulk_extraction.py` | 5 | Bulk extraction: complete data, partial data, gibberish input, no data |
| `conftest.py` | - | Shared fixtures: `GraphRunner` helper, mock LLM, sample form definitions |

### Running Tests

```bash
# From project root, with venv activated
python -m pytest backend/tests/ -v

# Run a specific test file
python -m pytest backend/tests/test_e2e.py -v

# Run tests matching a pattern
python -m pytest backend/tests/ -k "test_extraction" -v
```

### Test Architecture

Tests use a `GraphRunner` helper (from `conftest.py`) that:
1. Creates a compiled graph
2. Initializes state with a test form definition
3. Provides a `run_turn(user_message, tool_results)` method
4. Uses a mock LLM that returns pre-configured responses

---

## 12. Deployment

### Docker

The project includes a multi-stage Dockerfile:

```
Stage 1 (base):  python:3.12-slim + curl
Stage 2 (deps):  Install Python dependencies
Stage 3 (app):   Copy source code, expose port 8000
```

**Docker Compose** for local development:

```bash
cp .env.example .env   # Configure LLM credentials
docker compose up --build
```

- Mounts source code as volume for live reload
- Uses `--reload` flag for uvicorn
- Health check on `/api/health`

### Manual Deployment

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000

# Flutter Web (for testing/simulation)
cd flutter_web
flutter pub get
flutter run -d chrome
```

---

## 13. Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CUSTOM_LLM_API_ENDPOINT` | Yes | - | OpenAI-compatible chat completions URL |
| `CUSTOM_LLM_API_KEY` | Yes | - | API key / bearer token |
| `CUSTOM_LLM_MODEL_NAME` | No | `default` | Model identifier |
| `SESSION_TIMEOUT_SECONDS` | No | `1800` | Session expiry (30 min default) |
| `CORS_ALLOWED_ORIGINS` | No | `*` | Comma-separated allowed origins |
| `BACKEND_HOST` | No | `0.0.0.0` | Server bind host |
| `BACKEND_PORT` | No | `8000` | Server port |

### Python Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| langchain-core | >=0.3.0 | Core LangChain abstractions |
| langchain-openai | >=0.3.0 | OpenAI-compatible LLM integration |
| langgraph | >=0.2.0 | State machine framework |
| pydantic | >=2.0.0 | Data validation and models |
| python-dateutil | >=2.8.0 | Flexible date parsing |
| python-dotenv | >=1.0.0 | Environment variable loading |
| fastapi | >=0.115.0 | REST API framework |
| uvicorn | >=0.34.0 | ASGI server |
| pytest | >=8.0.0 | Testing framework |
| pytest-asyncio | >=0.24.0 | Async test support |
| httpx | >=0.28.0 | HTTP client for testing |

---

## 14. Data Flow Diagrams

### Complete Request Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            REQUEST LIFECYCLE                            │
│                                                                         │
│  Flutter App                                                            │
│  ┌─────────┐                                                            │
│  │ User    │                                                            │
│  │ types   │─── POST /api/chat ──▶┐                                    │
│  │ message │                       │                                    │
│  └─────────┘                       ▼                                    │
│                              ┌───────────┐                              │
│                              │ FastAPI   │                              │
│                              │ /api/chat │                              │
│                              └─────┬─────┘                              │
│                                    │                                    │
│                        ┌───────────┴───────────┐                        │
│                        │                       │                        │
│                   New session?            Existing?                     │
│                        │                       │                        │
│                        ▼                       ▼                        │
│               create_initial_state()    get_session()                   │
│               extract_required_fields    session.touch()                │
│               extract_field_type_map                                    │
│                        │                       │                        │
│                        └───────────┬───────────┘                        │
│                                    │                                    │
│                                    ▼                                    │
│                          prepare_turn_input()                           │
│                          (set user_message,                             │
│                           tool_results,                                 │
│                           reset ephemeral)                              │
│                                    │                                    │
│                                    ▼                                    │
│                          graph.ainvoke(state)                           │
│                                    │                                    │
│                              route_input()                              │
│                           ┌────┬───┴───┬────┬────┐                      │
│                           │    │       │    │    │                      │
│                           ▼    ▼       ▼    ▼    ▼                      │
│                         greet tool   valid extr  conv                   │
│                           │  handler input ction sation                 │
│                           │    │       │    │    │                      │
│                           │    └───┬───┘    │    │                      │
│                           │        │        │    │                      │
│                           │        ▼        │    │                      │
│                           │   conversation  │    │                      │
│                           │        │        │    │                      │
│                           │        └────┬───┘    │                      │
│                           │             │        │                      │
│                           │             ▼        │                      │
│                           │         finalize ◀───┘                      │
│                           │             │                               │
│                           └──────┬──────┘                               │
│                                  │                                      │
│                                  ▼                                      │
│                          result_state                                   │
│                          {action, answers,                              │
│                           conversation_history, ...}                    │
│                                  │                                      │
│                          session.state = result_state                   │
│                                  │                                      │
│                                  ▼                                      │
│                          ChatResponse                                   │
│                          {action, conversation_id, answers}             │
│                                  │                                      │
│  Flutter App                     │                                      │
│  ┌─────────┐◀────────────────────┘                                      │
│  │ Render  │                                                            │
│  │ action  │                                                            │
│  │ widget  │                                                            │
│  └─────────┘                                                            │
└─────────────────────────────────────────────────────────────────────────┘
```

### Answer Storage Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                     ANSWER STORAGE PATHS                         │
│                                                                  │
│  Path 1: Extraction (bulk)                                       │
│  ─────────────────────────                                       │
│  User: "I got injured Jan 15 at work"                            │
│       │                                                          │
│       ▼                                                          │
│  extraction node -> LLM extracts {injuryDate: "2026-01-15"}     │
│       │                                                          │
│       ▼                                                          │
│  Validate date format -> OK                                      │
│       │                                                          │
│       ▼                                                          │
│  answers = {injuryDate: "2026-01-15"}  ✓ Stored                 │
│                                                                  │
│  Path 2: Format-validated field (date, datetime)                 │
│  ──────────────────────────────────────────────                  │
│  AI asks: ASK_DATE for injuryDate                                │
│  User: "January 15 2026"                                         │
│       │                                                          │
│       ▼                                                          │
│  validate_input node -> dateutil parse -> OK                     │
│       │                                                          │
│       ▼                                                          │
│  answers = {injuryDate: "January 15 2026"}  ✓ Stored immediately│
│                                                                  │
│  Path 3: Context-validated field (text)                          │
│  ────────────────────────────────────                            │
│  AI asks: ASK_TEXT for injuryOccurred                            │
│  User: "asdfghjkl"                                               │
│       │                                                          │
│       ▼                                                          │
│  validate_input node -> HOLD (pending_text_value = "asdfghjkl") │
│       │                                                          │
│       ▼                                                          │
│  conversation node -> LLM sees "[VALIDATE this answer]"          │
│       │                                                          │
│       ├── LLM re-asks same field (gibberish rejected)            │
│       │        │                                                 │
│       │        ▼                                                 │
│       │   finalize -> DISCARD pending_text_value  ✗ Not stored  │
│       │                                                          │
│       └── LLM moves to next field (answer accepted)              │
│                │                                                 │
│                ▼                                                 │
│           finalize -> STORE pending_text_value   ✓ Stored       │
│                                                                  │
│  Path 4: Dropdown/Checkbox (from TOOL_CALL result)               │
│  ─────────────────────────────────────────────                   │
│  AI: TOOL_CALL get_establishments                                │
│  Frontend: executes, returns results                             │
│  AI: ASK_DROPDOWN with real options                              │
│  User: selects "Company A"                                       │
│       │                                                          │
│       ▼                                                          │
│  validate_input -> no special validation for dropdown            │
│       │                                                          │
│       ▼                                                          │
│  answers = {selectedEstablishment: "Company A"}  ✓ Stored       │
└──────────────────────────────────────────────────────────────────┘
```

---

## 15. Key Design Decisions

### 1. LangGraph over Custom State Machine

**Decision**: Use LangGraph (from LangChain) instead of a hand-rolled state machine.

**Why**:
- Explicit, inspectable graph topology (nodes + edges)
- Built-in state management with typed reducers
- Conditional routing with named functions
- Easy to add/remove/reorder nodes
- Integrates natively with LangChain LLM abstractions

### 2. Markdown over JSON Schema

**Decision**: Define forms as markdown documents instead of rigid JSON schemas.

**Why**:
- LLMs interpret markdown natively and well
- Maximum flexibility for complex business rules
- Can include examples, instructions, and conditional logic in natural language
- Human-readable and easy to author
- Extensible without backend code changes

**Trade-off**: Less type-safe than JSON schemas. The backend still parses the Field Summary Table for required fields and types.

### 3. Two-Phase Conversation Flow

**Decision**: First extract all possible values from a free-text description, then ask remaining fields one at a time.

**Why**:
- Minimizes back-and-forth (users can provide most data in one message)
- More natural conversation flow (feels like talking to a human)
- Falls back gracefully if extraction finds nothing

### 4. Frontend-Executed Tool Calls

**Decision**: The AI never calls APIs directly. It returns TOOL_CALL actions, and the frontend executes them.

**Why**:
- Separation of concerns: AI reasons, frontend acts
- Security: AI has no direct API access
- Flexibility: Frontend can use mock data, cached data, or real APIs
- Testability: Tool results can be easily mocked in tests

### 5. Dual Validation Strategy

**Decision**: Deterministic validation for dates, LLM-based validation for text.

**Why**:
- Dates have clear formats that can be checked programmatically (faster, more reliable)
- Text answers need contextual judgment (is "I like pizza" a valid injury description? Only the LLM can judge)
- The "hold and let LLM decide" pattern avoids storing gibberish while keeping the flow conversational

### 6. In-Memory Sessions

**Decision**: Store conversation state in memory, not a database.

**Why**:
- Simplicity (no database setup needed for development)
- Speed (no I/O overhead)
- Sufficient for demo/testing purposes

**Production note**: Should be replaced with Redis or similar for persistence and horizontal scaling.

### 7. Prompt Condensation

**Decision**: Condense large markdown forms before sending to the LLM.

**Why**:
- Small models (3B-8B parameters) lose track of output format instructions when the prompt is too long
- The Field Summary Table and Tool Calls sections contain the most critical information
- Detailed per-field descriptions can be omitted without losing functionality

### 8. Aggressive LLM Guards

**Decision**: Implement multiple guard checks after LLM responses, with automatic retries.

**Why**:
- Small models frequently make mistakes (wrong JSON, re-asking answered fields, empty options)
- Guards catch and correct these mistakes automatically (up to 3 retries)
- Each retry includes a very direct, blunt corrective message
- This makes the system work reliably even with smaller, less capable models

---

## Summary

FormPilot AI is a complete, production-ready conversational form-filling system that combines:

- **LangGraph state machine** for explicit, inspectable conversation flow
- **Markdown-driven form definitions** for maximum flexibility
- **Dual validation** (deterministic + LLM-based) for reliable data collection
- **Tool call round-trip** for secure external data access
- **Aggressive LLM guards** for reliability with smaller models
- **Flutter Web app** for testing and simulation
- **242 comprehensive tests** covering all components

The system is designed to be simple, maintainable, and reliable - following the core principle: "If unsure between simple & clear vs. flexible & complex, always choose simple & clear."

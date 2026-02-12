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
│       ├── models/           # Dart data models
│       ├── screens/          # App screens
│       ├── services/         # Backend communication
│       └── widgets/          # Reusable UI widgets
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

## Development Status

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Project Setup & Environment | Done |
| 1 | Form Schema Definition & Validation | Done |
| 2 | Deterministic Visibility Evaluator | Done |
| 3 | Form State Manager | Done |
| 4 | AI Action Protocol | Done |
| 5 | LangChain Structured Chat Agent | Done |
| 6 | Backend API Layer | Pending |
| 7 | Flutter Web App (Simulation & Testing) | Pending |
| 8 | Testing & Quality Assurance | Pending |
| 9 | Documentation & Deployment | Pending |

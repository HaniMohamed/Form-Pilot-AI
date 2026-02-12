# FormPilot AI - Detailed TODO Steps

> Generated from: `GenAI_Conversational_Form_Filling_System_Plan.md`
> Date: 2026-02-12

---

## Phase 0: Project Setup & Environment

- [ ] **0.1** Initialize the Python backend project structure
  - [ ] Create project root directories: `backend/`, `backend/core/`, `backend/agent/`, `backend/api/`, `backend/tests/`, `backend/schemas/`
  - [ ] Create `backend/requirements.txt` with pinned dependencies:
    - `langchain`, `langchain-openai`, `langchain-ibm` (watsonx)
    - `pydantic`
    - `python-dateutil`
    - `pytest`
  - [ ] Create `backend/pyproject.toml` or `setup.py` for project metadata
  - [ ] Set up a Python virtual environment and install dependencies
- [ ] **0.2** Initialize the Flutter web app project (simulation & testing UI)
  - [ ] Create the Flutter web app directory: `flutter_web/`
  - [ ] Add required Flutter dependencies in `pubspec.yaml`:
    - `http` (for backend communication)
    - `intl` (for date formatting)
    - `provider` or `riverpod` (for state management)
  - [ ] Enable web support: `flutter config --enable-web`
  - [ ] Run `flutter pub get`
- [ ] **0.3** Set up environment configuration
  - [ ] Create `.env.example` with placeholders for:
    - `LLM_PROVIDER` (watsonx / openai / azure_openai)
    - `LLM_API_KEY`
    - `LLM_MODEL_NAME`
    - `LLM_ENDPOINT` (for watsonx / Azure)
    - `BACKEND_HOST` / `BACKEND_PORT`
  - [ ] Create `.gitignore` covering Python (`__pycache__`, `.env`, `venv/`) and Flutter Web (`.dart_tool/`, `build/`)

---

## Phase 1: Form Schema Definition & Validation

- [ ] **1.1** Design the canonical form schema JSON structure
  - [ ] Define the top-level schema keys: `form_id`, `rules`, `fields`
  - [ ] Define the `rules.interaction` object with:
    - `ask_one_field_at_a_time: bool`
    - `never_assume_values: bool`
  - [ ] Document all supported keys per field:
    - `id` (string, unique)
    - `type` (enum: dropdown, checkbox, text, date, datetime, location)
    - `required` (bool)
    - `options` (list, for dropdown/checkbox)
    - `prompt` (string)
    - `visible_if` (object, optional)
- [ ] **1.2** Define the `visible_if` condition contract
  - [ ] Support `all` (AND logic) as a list of condition objects
  - [ ] Each condition object must include:
    - `field` (string, referencing another field's `id`)
    - `operator` (enum: EXISTS, EQUALS, NOT_EQUALS, AFTER, BEFORE, ON_OR_AFTER, ON_OR_BEFORE)
    - `value` (static comparison value, optional)
    - `value_field` (dynamic comparison referencing another field, optional)
- [ ] **1.3** Create Pydantic models for schema validation
  - [ ] `FormSchema` model (top-level)
  - [ ] `FormField` model (per field)
  - [ ] `InteractionRules` model
  - [ ] `VisibilityCondition` model
  - [ ] `VisibilityRule` model (wrapping `all` list)
  - [ ] Add validation: field IDs must be unique, referenced fields in `visible_if` must exist in the schema, `options` required for dropdown/checkbox types
- [ ] **1.4** Write unit tests for schema validation
  - [ ] Test valid schema passes validation
  - [ ] Test missing required keys are rejected
  - [ ] Test duplicate field IDs are rejected
  - [ ] Test `visible_if` referencing non-existent fields is rejected
  - [ ] Test dropdown/checkbox without `options` is rejected
  - [ ] Test unknown field `type` is rejected
- [ ] **1.5** Create example schema JSON files
  - [ ] `schemas/incident_report.json` (from the plan)
  - [ ] `schemas/leave_request.json` (additional test schema with varied field types)

---

## Phase 2: Deterministic Visibility Evaluator

- [ ] **2.1** Implement the visibility evaluation engine
  - [ ] Create `backend/core/visibility.py`
  - [ ] Implement `is_field_visible(field: dict, answers: dict) -> bool`
  - [ ] Handle the case where `visible_if` is absent (always visible)
  - [ ] Implement `all` (AND) logic: every condition must pass
- [ ] **2.2** Implement each operator
  - [ ] `EXISTS` — field has a non-None value in answers
  - [ ] `EQUALS` — field value equals `condition.value` or `answers[condition.value_field]`
  - [ ] `NOT_EQUALS` — field value does not equal the comparison
  - [ ] `AFTER` — `parse_date(field_value) > parse_date(compare_value)`
  - [ ] `BEFORE` — `parse_date(field_value) < parse_date(compare_value)`
  - [ ] `ON_OR_AFTER` — `parse_date(field_value) >= parse_date(compare_value)`
  - [ ] `ON_OR_BEFORE` — `parse_date(field_value) <= parse_date(compare_value)`
- [ ] **2.3** Implement date parsing utility
  - [ ] Create `backend/core/utils.py`
  - [ ] Implement `parse_date(value: str) -> date` supporting ISO 8601 (`YYYY-MM-DD`) and datetime strings
  - [ ] Handle invalid/unparseable dates gracefully (return `None` or raise)
- [ ] **2.4** Write unit tests for the visibility evaluator
  - [ ] Test field with no `visible_if` is always visible
  - [ ] Test `EXISTS` passes when value present, fails when absent
  - [ ] Test `EQUALS` with static value
  - [ ] Test `EQUALS` with `value_field` (dynamic comparison)
  - [ ] Test `NOT_EQUALS` with static and dynamic values
  - [ ] Test `AFTER` / `BEFORE` with valid dates
  - [ ] Test `ON_OR_AFTER` / `ON_OR_BEFORE` edge cases (same date)
  - [ ] Test `all` logic with multiple conditions (all must pass)
  - [ ] Test with missing referenced field in answers (should return False)

---

## Phase 3: Form State Manager

- [ ] **3.1** Implement the form state manager
  - [ ] Create `backend/core/form_state.py`
  - [ ] Implement `FormStateManager` class with:
    - `schema: FormSchema` (loaded and validated)
    - `answers: dict` (current user answers, keyed by field `id`)
    - `conversation_history: list` (list of message dicts)
- [ ] **3.2** Implement field resolution logic
  - [ ] `get_visible_fields() -> list[FormField]` — filter fields by visibility using the evaluator
  - [ ] `get_missing_required_fields() -> list[FormField]` — visible + required + not yet answered
  - [ ] `get_next_field() -> FormField | None` — return the first missing required visible field (or `None` if form is complete)
- [ ] **3.3** Implement answer management
  - [ ] `set_answer(field_id: str, value: Any) -> None` — store user answer
  - [ ] `get_answer(field_id: str) -> Any` — retrieve current answer
  - [ ] `clear_answer(field_id: str) -> None` — remove an answer (for corrections)
  - [ ] `is_complete() -> bool` — all visible required fields have answers
- [ ] **3.4** Implement answer validation per field type
  - [ ] `dropdown` — value must be one of the defined `options`
  - [ ] `checkbox` — value(s) must be subset of defined `options`
  - [ ] `text` — non-empty string
  - [ ] `date` — valid ISO date string
  - [ ] `datetime` — valid ISO datetime string
  - [ ] `location` — dict with `lat` (float) and `lng` (float)
- [ ] **3.5** Handle cascading visibility changes
  - [ ] When an answer changes, re-evaluate visibility of all downstream fields
  - [ ] If a previously answered field becomes hidden, optionally clear its answer
- [ ] **3.6** Write unit tests for form state manager
  - [ ] Test loading a valid schema
  - [ ] Test `get_next_field` returns fields in order
  - [ ] Test `set_answer` updates state correctly
  - [ ] Test `is_complete` returns False when fields are missing
  - [ ] Test `is_complete` returns True when all required visible fields are answered
  - [ ] Test cascading visibility (answering field A reveals field B)
  - [ ] Test answer validation rejects invalid dropdown values
  - [ ] Test answer validation rejects malformed dates
  - [ ] Test answer clearing and re-evaluation

---

## Phase 4: AI Action Protocol (Structured Output)

- [ ] **4.1** Define the action types as Python enums/models
  - [ ] Create `backend/core/actions.py`
  - [ ] Define action enum: `ASK_DROPDOWN`, `ASK_CHECKBOX`, `ASK_TEXT`, `ASK_DATE`, `ASK_DATETIME`, `ASK_LOCATION`, `FORM_COMPLETE`, `MESSAGE`
  - [ ] Create Pydantic models for each action:
    - `AskDropdownAction(action, field_id, label, options)`
    - `AskCheckboxAction(action, field_id, label, options)`
    - `AskTextAction(action, field_id, label)`
    - `AskDateAction(action, field_id, label)`
    - `AskDatetimeAction(action, field_id, label)`
    - `AskLocationAction(action, field_id, label)`
    - `FormCompleteAction(action, data: dict)`
    - `MessageAction(action, text: str)` — for conversational responses
- [ ] **4.2** Implement action builder
  - [ ] `build_action_for_field(field: FormField) -> dict` — map field type to the correct action JSON
  - [ ] Ensure `options` are included for dropdown/checkbox
  - [ ] Ensure `label` is populated from field `prompt`
- [ ] **4.3** Implement `FORM_COMPLETE` payload builder
  - [ ] `build_completion_payload(answers: dict) -> dict` — assemble final data
  - [ ] Include all answered fields (visible ones only)
  - [ ] Format dates as ISO strings
  - [ ] Format location as `{ "lat": float, "lng": float }`
- [ ] **4.4** Write unit tests for action protocol
  - [ ] Test action builder produces correct JSON for each field type
  - [ ] Test `FORM_COMPLETE` payload includes all visible answered fields
  - [ ] Test `FORM_COMPLETE` excludes hidden fields

---

## Phase 5: LangChain Structured Chat Agent

- [ ] **5.1** Configure the LLM provider abstraction
  - [ ] Create `backend/agent/llm_provider.py`
  - [ ] Implement factory function `get_llm(provider: str, **kwargs)` supporting:
    - `openai` → `ChatOpenAI`
    - `azure_openai` → `AzureChatOpenAI`
    - `watsonx` → `WatsonxLLM` from `langchain_ibm`
    - `custom` → `ChatOpenAI` with custom `base_url` (OpenAI-compatible endpoints like GOSI Brain)
  - [ ] Load credentials from environment variables
  - [ ] Set sensible defaults: `temperature=0`, `max_tokens=1024`
- [ ] **5.2** Design the system prompt
  - [ ] Create `backend/agent/prompts.py`
  - [ ] Write a system prompt that instructs the LLM to:
    - Act as a form-filling assistant
    - Always ask one field at a time
    - Never assume or fabricate values
    - Respond with structured JSON actions only
    - Use the provided field prompt as the question
    - Handle user corrections gracefully
    - Output `FORM_COMPLETE` when all fields are filled
  - [ ] Include dynamic context injection points for:
    - Current schema (field list)
    - Current answers
    - Next required field
    - Available options (for dropdown/checkbox)
- [ ] **5.3** Build the conversation orchestrator
  - [ ] Create `backend/agent/orchestrator.py`
  - [ ] Implement `FormOrchestrator` class:
    - Takes `FormStateManager` and LLM instance
    - `process_user_message(user_message: str) -> dict` main entry point
  - [ ] Orchestration flow:
    1. Receive user message
    2. Parse user intent (answer to current field, correction request, general question)
    3. If answer: validate and store via `FormStateManager`
    4. Re-evaluate visibility
    5. If form complete: return `FORM_COMPLETE` action
    6. Otherwise: get next field and return appropriate `ASK_*` action
- [ ] **5.4** Implement user message interpretation
  - [ ] For `dropdown` fields: match user input to closest option (case-insensitive, partial match via LLM)
  - [ ] For `date`/`datetime` fields: parse natural language dates ("next Monday", "Feb 15") via LLM into ISO format
  - [ ] For `text` fields: accept raw user input
  - [ ] For `location` fields: instruct Flutter to open location picker (no text parsing)
  - [ ] For `checkbox` fields: accept multiple selections
- [ ] **5.5** Implement correction handling
  - [ ] Detect when user wants to change a previous answer ("go back", "change incident type", "actually it was...")
  - [ ] Clear the relevant answer in `FormStateManager`
  - [ ] Re-ask the corrected field
  - [ ] Re-evaluate visibility after correction
- [ ] **5.6** Implement conversation history management
  - [ ] Store messages in `FormStateManager.conversation_history`
  - [ ] Include system context, user messages, and assistant responses
  - [ ] Limit context window to prevent token overflow (sliding window or summarization)
- [ ] **5.7** Ensure LLM output is always valid JSON
  - [ ] Parse LLM output as JSON
  - [ ] If parsing fails, retry with a corrective prompt (max 2 retries)
  - [ ] If still invalid, return a fallback `MESSAGE` action with an error explanation
- [ ] **5.8** Write unit tests for the orchestrator
  - [ ] Test happy path: answer each field sequentially until `FORM_COMPLETE`
  - [ ] Test correction flow: change a previously answered field
  - [ ] Test visibility cascade: answering a field reveals a new conditional field
  - [ ] Test invalid dropdown value is rejected gracefully
  - [ ] Test LLM JSON parse failure triggers retry
  - [ ] Test conversation history is maintained correctly

---

## Phase 6: Backend API Layer

- [ ] **6.1** Create the API module
  - [ ] Create `backend/api/routes.py`
  - [ ] Implement a `/chat` endpoint (POST):
    - **Request body**: `{ "form_schema": {...}, "answers": {...}, "user_message": "...", "conversation_id": "..." }`
    - **Response body**: `{ "action": {...}, "conversation_id": "...", "answers": {...} }`
  - [ ] Implement a `/validate-schema` endpoint (POST):
    - **Request body**: `{ "form_schema": {...} }`
    - **Response body**: `{ "valid": bool, "errors": [...] }`
- [ ] **6.2** Implement conversation session management
  - [ ] Create `backend/core/session.py`
  - [ ] Maintain in-memory session store: `dict[conversation_id, FormStateManager]`
  - [ ] Auto-create session on first message
  - [ ] Support session cleanup/timeout
- [ ] **6.3** Add error handling and response formatting
  - [ ] Return proper HTTP status codes (400 for bad schema, 500 for LLM errors)
  - [ ] Return structured error responses: `{ "error": "...", "detail": "..." }`
- [ ] **6.4** Write integration tests for the API
  - [ ] Test `/validate-schema` with valid and invalid schemas
  - [ ] Test `/chat` full conversation flow
  - [ ] Test session persistence across multiple `/chat` calls
  - [ ] Test error responses for malformed requests

---

## Phase 7: Flutter Web App (Simulation & Testing UI)

- [ ] **7.1** Set up the Flutter web app structure
  - [ ] Create `flutter_web/` project (if not done in Phase 0)
  - [ ] Set up a clean project structure:
    - `lib/screens/` — main screens
    - `lib/widgets/` — reusable UI widgets
    - `lib/services/` — backend communication
    - `lib/models/` — data models
  - [ ] Configure web-specific settings in `web/index.html`
- [ ] **7.2** Build the chat service (backend communication)
  - [ ] Create `flutter_web/lib/services/chat_service.dart`
  - [ ] Implement `sendMessage(formSchema, answers, userMessage, conversationId)` calling the backend `/chat` endpoint
  - [ ] Handle network errors and timeouts gracefully
- [ ] **7.3** Build the action and schema models
  - [ ] Create `flutter_web/lib/models/form_schema.dart` — Dart models for `FormSchema`, `FormField`, `VisibilityCondition`
  - [ ] Create `flutter_web/lib/models/ai_action.dart` — Dart models for each action type
  - [ ] Implement `fromJson` / `toJson` serialization
- [ ] **7.4** Build the main simulation screen (three-panel layout)
  - [ ] Create `flutter_web/lib/screens/simulation_screen.dart`
  - [ ] Layout with three panels:
    1. **Chat panel** (left) — message list + text input
    2. **Dynamic widget panel** (center) — rendered from AI actions
    3. **JSON debug panel** (right) — current answers + last action + field visibility
  - [ ] Use responsive layout suitable for browser viewing
- [ ] **7.5** Implement schema loading
  - [ ] Add a dropdown or file picker to select/upload a schema JSON file
  - [ ] On load: send schema to backend, initialize a new session
  - [ ] Display form field summary in the debug panel
- [ ] **7.6** Implement the chat interaction loop
  - [ ] User types a message in the chat panel
  - [ ] Send to the backend `/chat` endpoint
  - [ ] Display the AI's conversational response in the chat panel
  - [ ] Render the returned action in the dynamic widget panel
- [ ] **7.7** Render dynamic widgets from AI actions
  - [ ] `ASK_DROPDOWN` → Flutter `DropdownButton` / `DropdownButtonFormField`
  - [ ] `ASK_CHECKBOX` → Flutter `CheckboxListTile` group
  - [ ] `ASK_TEXT` → Flutter `TextField`
  - [ ] `ASK_DATE` → Flutter `showDatePicker()` or date input widget
  - [ ] `ASK_DATETIME` → Flutter `showDatePicker()` + `showTimePicker()`
  - [ ] `ASK_LOCATION` → Text input for lat/lng (simulation mode)
  - [ ] `FORM_COMPLETE` → Display final JSON payload and a "Submit" button
- [ ] **7.8** Implement the JSON debug panel
  - [ ] Show current `answers` dict in real-time
  - [ ] Show the last AI action JSON
  - [ ] Show visible/hidden field status
  - [ ] Collapsible sections for each debug category
- [ ] **7.9** Add reset and debug controls
  - [ ] "Reset Conversation" button — clears session and starts over
  - [ ] "Show Schema" button — displays raw schema JSON in a dialog
  - [ ] "Show Conversation History" button — displays full message log
- [ ] **7.10** Test the Flutter web app end-to-end
  - [ ] Walk through the incident report schema manually
  - [ ] Verify dropdown options render correctly
  - [ ] Verify conditional fields appear/disappear based on answers
  - [ ] Verify `FORM_COMPLETE` shows correct final payload
  - [ ] Verify correction flow works (change a previous answer)
  - [ ] Verify responsive layout works at different browser sizes

---

## Phase 8: Testing & Quality Assurance

- [ ] **8.1** Write end-to-end tests
  - [ ] Full conversation flow: schema → first question → all answers → `FORM_COMPLETE`
  - [ ] Correction flow: answer, go back, change, re-evaluate
  - [ ] Conditional visibility flow: answers trigger hidden fields to appear
  - [ ] Edge case: all fields optional, form completes immediately
  - [ ] Edge case: user sends gibberish, AI asks to clarify
- [ ] **8.2** Write boundary and edge-case tests
  - [ ] Schema with 0 fields
  - [ ] Schema with 50+ fields (performance)
  - [ ] Deeply nested `visible_if` dependencies (field C depends on B depends on A)
  - [ ] Circular `visible_if` references (should be caught in validation)
  - [ ] Date edge cases: leap year, end of month, timezone boundaries
- [ ] **8.3** LLM output resilience tests
  - [ ] Test with malformed LLM JSON responses
  - [ ] Test with unexpected LLM keys in response
  - [ ] Test LLM returning actions for wrong field
  - [ ] Test LLM timeout/failure handling
- [ ] **8.4** Performance testing
  - [ ] Measure response latency per conversation turn
  - [ ] Test with concurrent sessions (10, 50, 100)
  - [ ] Monitor token usage per conversation

---

## Phase 9: Documentation & Deployment

- [ ] **9.1** Write project documentation
  - [ ] `README.md` — project overview, setup instructions, architecture diagram
  - [ ] `docs/schema_guide.md` — how to write a form schema
  - [ ] `docs/api_reference.md` — backend API endpoints and contracts
  - [ ] `docs/action_protocol.md` — full list of AI actions and their JSON formats
- [ ] **9.2** Add inline code documentation
  - [ ] Docstrings for all Python classes and public methods
  - [ ] Dart doc comments for all Flutter web app classes and public methods
- [ ] **9.3** Containerize the backend
  - [ ] Create `Dockerfile` for the Python backend
  - [ ] Create `docker-compose.yml` for local development (backend + optional services)
- [ ] **9.4** Set up CI/CD pipeline
  - [ ] Python: lint (`ruff` or `flake8`), format (`black`), test (`pytest`)
  - [ ] Flutter Web: lint (`flutter analyze`), format (`dart format`), test (`flutter test`)
  - [ ] Run on every PR / push
- [ ] **9.5** Deployment configuration
  - [ ] Environment variable documentation for production
  - [ ] Backend deployment guide (Docker / cloud platform)
  - [ ] Flutter web app build and hosting configuration

---

## Summary Checklist

| Phase | Description                            | Status |
|-------|----------------------------------------|--------|
| 0     | Project Setup & Environment            | [ ]    |
| 1     | Form Schema Definition & Validation    | [ ]    |
| 2     | Deterministic Visibility Evaluator     | [ ]    |
| 3     | Form State Manager                     | [ ]    |
| 4     | AI Action Protocol                     | [ ]    |
| 5     | LangChain Structured Chat Agent        | [ ]    |
| 6     | Backend API Layer                      | [ ]    |
| 7     | Flutter Web App (Simulation & Testing) | [ ]    |
| 8     | Testing & Quality Assurance            | [ ]    |
| 9     | Documentation & Deployment             | [ ]    |

---

> **Note:** Phases 1-6 are backend-focused and can proceed independently.
> Phase 7 (Flutter Web App) serves as the primary testing, debugging, and demo tool.
> Phase 7 can begin once the API contract (Phase 6) is defined.

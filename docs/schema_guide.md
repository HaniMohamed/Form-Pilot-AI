# Form Schema Guide

How to write a form definition for FormPilot AI using the **hybrid format**: structured YAML frontmatter for field/tool metadata, plus a markdown body for rich LLM instructions.

---

## Format Overview

Every form definition is a single `.md` file with two sections:

```
---
(YAML frontmatter — structured data the code parses)
---

(Markdown body — rich instructions the LLM reads)
```

**Why this format?**

| Section | Parsed by | Purpose |
|---------|-----------|---------|
| YAML frontmatter | Backend code (deterministic) | Field IDs, types, required flags, tool definitions |
| Markdown body | LLM (conversational) | Business rules, conditional logic, display behavior, tone |

The code reads the frontmatter to know *what fields exist and what type they are*. The LLM reads the markdown to know *how to ask about them*.

---

## YAML Frontmatter Reference

The frontmatter block starts and ends with `---` and uses standard YAML syntax.

### Top-Level Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `form_id` | string | Yes | Unique identifier for the form |
| `title` | string | Yes | Human-readable form title |
| `purpose` | string | No | One-line description of what the form does |
| `language` | string | No | Language support (e.g. `"bilingual (Arabic / English)"`) |
| `fields` | list | Yes | Ordered list of field definitions |
| `tools` | list | No | Tool call definitions (for data fetching) |

### Field Definition

Each entry in the `fields` list defines one form field.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `id` | string | Yes | Unique field identifier (used in code and LLM responses) |
| `type` | string | Yes | Field type (see supported types below) |
| `required` | bool or string | Yes | `true`, `false`, or `"conditional"` |
| `step` | number | No | Which form step this field belongs to |
| `prompt` | string | Yes | The question to ask the user |
| `options` | list | Conditional | Static options (required for dropdowns with static data) |
| `default` | string | No | Default value |
| `data_source` | string | No | Tool name that provides dynamic options |
| `depends_on` | string | No | Field ID this field depends on |
| `visible_if` | string | No | Condition for when this field is visible |
| `constraints` | string | No | Validation constraints in plain language |
| `validation` | string | No | Input format rules |

### Supported Field Types

| Type | Description | LLM Action |
|------|-------------|------------|
| `text` | Free text input | `ASK_TEXT` |
| `dropdown` | Single-select from options | `ASK_DROPDOWN` |
| `checkbox` | Multi-select from options | `ASK_CHECKBOX` |
| `date` | Date picker | `ASK_DATE` |
| `datetime` | Date + time picker | `ASK_DATETIME` |
| `time` | Time input | `ASK_TEXT` (parsed by LLM) |
| `location` | Map pin / coordinates | `ASK_LOCATION` or `TOOL_CALL` |
| `file` | File upload | `TOOL_CALL` (triggers native picker) |

### Required Field Values

| Value | Meaning |
|-------|---------|
| `true` | Always required. The backend tracks it as a required field. |
| `false` | Optional. The LLM may ask but won't block completion. |
| `"conditional"` | Required only when a condition is met. The LLM evaluates the condition from the markdown body. The backend does NOT track it as required. |

### Tool Definition

Each entry in the `tools` list defines a tool the AI can call.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `name` | string | Yes | Tool name (must match frontend implementation) |
| `purpose` | string | Yes | What this tool does |
| `when` | string | Yes | When the AI should call this tool |
| `args` | object | No | Expected arguments (key: type pairs) |
| `returns` | string | Yes | Description of the return format |

---

## Markdown Body Reference

The markdown body below the frontmatter is sent to the LLM as conversational context. Write it as clear instructions for the AI agent.

### Recommended Sections

| Section | Purpose |
|---------|---------|
| **Form Overview** | Purpose, language, flow summary |
| **Step N: [Title]** | Per-step field details, display logic, validation rules |
| **Conditional Logic Summary** | Table of conditions and their effects |
| **Chat Agent Instructions** | Step-by-step flow, critical rules, tone guidance |

### Writing Effective Field Descriptions

For each field in the markdown body, describe:

1. **What the AI does** — Step-by-step behavior (call tool, present options, validate)
2. **Display logic** — How to present data (bilingual names, formatting)
3. **Validation rules** — What makes an answer valid or invalid
4. **Edge cases** — What happens on corrections, resets, dependencies

### Writing Tool Call Instructions

For fields that require tool data:

1. State clearly: "Call `tool_name` FIRST — you need the data before asking."
2. Describe the response format the AI should expect.
3. Explain how to present the data to the user.

### Writing Conditional Logic

Use a summary table for all conditions:

```markdown
| Condition | Effect |
|---|---|
| Field A selected | Show Field B |
| Date gap >= 7 days | Require delay reason |
| Feature flag X is ON | Hide document upload |
```

---

## Complete Example

Below is a minimal but complete form definition.

```yaml
---
form_id: leave_request
title: Leave Request
purpose: Employee submits a leave request.

fields:
  - id: leave_type
    type: dropdown
    required: true
    prompt: "What type of leave are you requesting?"
    options: ["Annual", "Sick", "Emergency"]

  - id: start_date
    type: date
    required: true
    prompt: "When does your leave start?"

  - id: end_date
    type: date
    required: true
    prompt: "When does your leave end?"
    constraints: "Must be on or after start_date."

  - id: reason
    type: text
    required: true
    prompt: "Why are you requesting leave?"

  - id: medical_certificate
    type: dropdown
    required: "conditional"
    prompt: "Do you have a medical certificate?"
    options: ["Yes", "No"]
    visible_if: "leave_type == Sick"

tools: []
---

# Leave Request

## Form Overview

- **Purpose**: Employee submits a leave request.
- **Flow**: Single step. All fields collected in order.

## Fields

### Leave Type (REQUIRED)

Ask the user to select the type of leave. Present all three options.

### Start Date (REQUIRED)

Ask for the leave start date. Must be a valid date.

### End Date (REQUIRED)

Must be on or after the start date. If the user provides an end date
before the start date, ask them to correct it.

### Reason (REQUIRED)

Free text. The answer must be a genuine reason, not gibberish.

### Medical Certificate (CONDITIONAL)

Only ask this if the leave type is "Sick". If the leave type is
Annual or Emergency, skip this field entirely.

## Chat Agent Instructions

1. Ask fields in order: leave_type -> start_date -> end_date -> reason.
2. If leave_type is "Sick", also ask medical_certificate.
3. Return FORM_COMPLETE when all required visible fields are answered.
4. Be professional and concise.
```

---

## Tips for Writing Effective Schemas

### Keep the frontmatter focused on data

The frontmatter should answer: *What fields exist, what types are they, and what tools are available?* Don't put business logic here — that goes in the markdown body.

### Keep the markdown focused on behavior

The markdown should answer: *How should the AI behave when collecting this field?* Include display logic, validation rules, error handling, and tone guidance.

### Use `data_source` for dynamic options

If a dropdown's options come from an API, set `data_source` to the tool name. Don't list fake options in `options`. The AI will call the tool first, then present real data.

```yaml
- id: establishment
  type: dropdown
  required: true
  prompt: "Select your establishment"
  data_source: get_establishments  # AI calls this tool first
```

### Use `"conditional"` for fields that aren't always required

Fields with `required: "conditional"` won't be tracked as required by the backend. The LLM decides whether to ask based on the condition described in the markdown body.

```yaml
- id: delay_reason
  type: text
  required: "conditional"
  prompt: "Why was there a delay?"
  visible_if: "informed_date - injury_date >= 7 days"
```

### Order fields by conversation flow

List fields in the order the AI should ask them. The backend uses this order to determine what to ask next.

### Write bilingual prompts when needed

If the form supports multiple languages, note it in the markdown body. The AI will respond in the user's language.

---

## File Location

Place form definition files in `backend/schemas/`. The API serves them via:

- `GET /api/schemas` — list all available `.md` files
- `GET /api/schemas/{filename}` — get a specific file's content

# GenAI Conversational Form Filling System (Schema-Driven, No RAG)
project name is `FormPilot AI`

## 1. Objective

Build a GenAI-powered conversational agent that helps users fill complex
Flutter forms via chat while strictly following existing business logic
and UI behavior.

The AI: - Does NOT call APIs - Does NOT submit forms - Does NOT
interpret business logic freely - Orchestrates form completion
step-by-step - Returns structured UI actions to the web app - Ends by
returning a final JSON payload for user review and submission

------------------------------------------------------------------------

## 2. High-Level Architecture

### Flutter Web App (Simulation & Testing)

-   Simulates form-filling behavior in a browser
-   Chat panel for conversational interaction
-   Dynamic widget rendering from AI actions
-   JSON debug panel for inspecting state and actions
-   Used for development, testing, and demos

### Backend (Python)

-   LangChain structured chat agent
-   Deterministic form state & visibility evaluator
-   Conversation state manager

### LLM

-   watsonx / OpenAI / Azure OpenAI / Custom OpenAI-compatible (e.g. GOSI Brain)
-   Used only for reasoning and structured output
-   No tool calling, no API access

------------------------------------------------------------------------

## 3. Core Design Principles

1.  Schema Is the Single Source of Truth
    -   All rules are encoded in JSON\
    -   No textual business logic\
    -   No RAG
2.  Deterministic Logic, Probabilistic Language
    -   All conditions are evaluated in code\
    -   AI only reacts to evaluated state
3.  One Field at a Time
    -   The agent always asks for exactly one missing field\
    -   Never assumes values\
    -   Never skips required fields

------------------------------------------------------------------------

## 4. Form Schema Contract (Web App → AI)

Example:

``` json
{
  "form_id": "incident_report",
  "rules": {
    "interaction": {
      "ask_one_field_at_a_time": true,
      "never_assume_values": true
    }
  },
  "fields": [
    {
      "id": "incident_type",
      "type": "dropdown",
      "required": true,
      "options": ["Fire", "Accident", "Injury"],
      "prompt": "What is the incident type?"
    },
    {
      "id": "start_date",
      "type": "date",
      "required": true,
      "prompt": "Please select the start date"
    },
    {
      "id": "end_date",
      "type": "date",
      "required": true,
      "prompt": "Please select the end date"
    },
    {
      "id": "followup_reason",
      "type": "text",
      "required": true,
      "prompt": "Please explain why a follow-up is required",
      "visible_if": {
        "all": [
          { "field": "start_date", "operator": "EXISTS" },
          { "field": "end_date", "operator": "EXISTS" },
          {
            "field": "end_date",
            "operator": "AFTER",
            "value_field": "start_date"
          }
        ]
      }
    },
    {
      "id": "location",
      "type": "location",
      "required": true,
      "prompt": "Please select the incident location"
    }
  ]
}
```

------------------------------------------------------------------------

## 5. Supported Field Types

-   dropdown
-   checkbox
-   text
-   date
-   datetime
-   location

------------------------------------------------------------------------

## 6. Visibility Condition System

### Supported Operators

-   EXISTS
-   EQUALS
-   NOT_EQUALS
-   AFTER
-   BEFORE
-   ON_OR_AFTER
-   ON_OR_BEFORE

All operators are evaluated in backend code, NOT by the LLM.

------------------------------------------------------------------------

## 7. Deterministic Visibility Evaluation (Pseudo-Code)

``` python
def is_field_visible(field, answers):
    if "visible_if" not in field:
        return True

    for condition in field["visible_if"]["all"]:
        value = answers.get(condition["field"])

        if condition["operator"] == "EXISTS":
            if value is None:
                return False

        elif condition["operator"] == "AFTER":
            compare = answers.get(condition["value_field"])
            if not value or not compare:
                return False
            if parse_date(value) <= parse_date(compare):
                return False

    return True
```

------------------------------------------------------------------------

## 8. AI ↔ Web App Action Protocol

### ASK_DROPDOWN

``` json
{
  "action": "ASK_DROPDOWN",
  "field_id": "incident_type",
  "label": "What is the incident type?",
  "options": ["Fire", "Accident", "Injury"]
}
```

### ASK_DATE

``` json
{
  "action": "ASK_DATE",
  "field_id": "start_date",
  "label": "Please select the start date"
}
```

### ASK_LOCATION

``` json
{
  "action": "ASK_LOCATION",
  "field_id": "location",
  "label": "Please select the incident location"
}
```

### ASK_TEXT

``` json
{
  "action": "ASK_TEXT",
  "field_id": "followup_reason",
  "label": "Please explain why a follow-up is required"
}
```

------------------------------------------------------------------------

## 9. Conversation Flow

1.  Web app sends schema + answers + user message\
2.  Backend evaluates visibility and missing fields\
3.  AI selects next field and returns one action\
4.  Web app executes UI action and returns value\
5.  Repeat until complete

------------------------------------------------------------------------

## 10. Completion Response

``` json
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
  }
}
```

Web App: - Displays completed form data - Shows review screen - Allows re-submission or reset

------------------------------------------------------------------------

## 11. Flutter Web App (Simulation & Testing UI)

Purpose: - Simulate Flutter mobile app behavior in a browser - Validate
agent logic - Debug structured JSON - Serve as a demo and testing
interface

Components: - Chat panel (conversational form filling) - Dynamic
widgets rendered from AI actions (dropdown, date picker, text input,
etc.) - JSON debug panel (current answers, last action, field
visibility) - Schema selector / loader - Reset and debug controls

------------------------------------------------------------------------

## 12. Non-Goals

-   AI does NOT validate business rules beyond schema
-   AI does NOT call APIs
-   AI does NOT submit data
-   AI does NOT infer hidden fields

------------------------------------------------------------------------

## 13. Implementation Steps

1.  Validate schema structure
2.  Implement visibility evaluator
3.  Implement form state manager
4.  Build structured LangChain agent
5.  Build Flutter web app (simulation & testing UI)

------------------------------------------------------------------------

## 14. Golden Rules

-   If logic can be expressed in JSON → encode it in schema\
-   If logic can be expressed in code → never let AI decide it\
-   AI output must always be machine-consumable

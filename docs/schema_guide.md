# Form Schema Guide

This guide explains how to write a form schema for FormPilot AI. The schema is a JSON file that defines the fields, types, options, and visibility rules for a form.

## Schema Structure

```json
{
  "form_id": "my_form",
  "rules": {
    "interaction": {
      "ask_one_field_at_a_time": true,
      "never_assume_values": true
    }
  },
  "fields": [ ... ]
}
```

### Top-Level Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `form_id` | string | Yes | Unique identifier for the form |
| `rules` | object | No | Interaction rules (currently informational) |
| `fields` | array | Yes | List of form field definitions (min: 1) |

## Field Definition

Each field in the `fields` array has the following structure:

```json
{
  "id": "leave_type",
  "type": "dropdown",
  "required": true,
  "options": ["Annual", "Sick", "Emergency"],
  "prompt": "What type of leave are you requesting?",
  "visible_if": { ... }
}
```

### Field Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `id` | string | Yes | Unique field identifier (no duplicates) |
| `type` | string | Yes | Field type (see supported types below) |
| `required` | boolean | Yes | Whether the field must be answered |
| `prompt` | string | Yes | Question text shown to the user |
| `options` | array | Conditional | Required for `dropdown` and `checkbox` types |
| `visible_if` | object | No | Visibility conditions (field is always visible if absent) |

### Supported Field Types

| Type | Value Format | `options` Required | Description |
|------|-------------|-------------------|-------------|
| `dropdown` | string (one of options) | Yes | Single-select dropdown |
| `checkbox` | array of strings (subset of options) | Yes | Multi-select checkboxes |
| `text` | string (non-empty) | No | Free text input |
| `date` | string (ISO 8601: `YYYY-MM-DD`) | No | Date picker |
| `datetime` | string (ISO 8601: `YYYY-MM-DDTHH:MM:SS`) | No | Date + time picker |
| `location` | object: `{"lat": number, "lng": number}` | No | Location picker |

## Visibility Conditions

Fields can be conditionally visible based on other fields' values. Use `visible_if` with an `all` array (AND logic — every condition must pass).

### Basic Structure

```json
"visible_if": {
  "all": [
    { "field": "some_field", "operator": "EQUALS", "value": "some_value" }
  ]
}
```

### Condition Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `field` | string | Yes | ID of the field to evaluate |
| `operator` | string | Yes | Comparison operator (see below) |
| `value` | string | No | Static comparison value |
| `value_field` | string | No | Dynamic comparison — another field's ID |

> Note: Use `value` for static comparisons or `value_field` for dynamic comparisons. For `EXISTS`, neither is needed.

### Supported Operators

| Operator | Description | Requires |
|----------|-------------|----------|
| `EXISTS` | Field has any value | Nothing extra |
| `EQUALS` | Field equals comparison value | `value` or `value_field` |
| `NOT_EQUALS` | Field does not equal comparison | `value` or `value_field` |
| `AFTER` | Date is after comparison date | `value` or `value_field` |
| `BEFORE` | Date is before comparison date | `value` or `value_field` |
| `ON_OR_AFTER` | Date is on or after comparison | `value` or `value_field` |
| `ON_OR_BEFORE` | Date is on or before comparison | `value` or `value_field` |

**Important:** All visibility conditions are evaluated deterministically in backend code, never by the LLM.

### Multiple Conditions (AND Logic)

All conditions in the `all` array must pass for the field to be visible:

```json
"visible_if": {
  "all": [
    { "field": "start_date", "operator": "EXISTS" },
    { "field": "end_date", "operator": "EXISTS" },
    { "field": "end_date", "operator": "AFTER", "value_field": "start_date" }
  ]
}
```

This means: the field is visible only when `start_date` exists AND `end_date` exists AND `end_date` is after `start_date`.

## Validation Rules

The backend validates schemas with these constraints:

1. **Unique IDs** — Every field must have a unique `id`
2. **Valid references** — `visible_if` conditions must reference fields that exist in the schema
3. **No self-reference** — A field cannot reference itself in `visible_if`
4. **Options required** — `dropdown` and `checkbox` fields must have an `options` array
5. **At least one field** — The `fields` array must not be empty

Use the `POST /api/validate-schema` endpoint to check a schema before using it.

## Cascading Visibility

When an answer changes (e.g., a correction), the system re-evaluates visibility of all fields. If a previously visible field becomes hidden:
- Its answer is automatically cleared
- Any fields that depended on that answer are also re-evaluated (cascading)

## Examples

### Conditional Field (Equals)

Show `medical_certificate` only when `leave_type` is "Sick":

```json
{
  "id": "medical_certificate",
  "type": "checkbox",
  "required": true,
  "options": ["Yes", "No"],
  "prompt": "Do you have a medical certificate?",
  "visible_if": {
    "all": [
      { "field": "leave_type", "operator": "EQUALS", "value": "Sick" }
    ]
  }
}
```

### Date Comparison

Show `followup_reason` only when `end_date` is after `start_date`:

```json
{
  "id": "followup_reason",
  "type": "text",
  "required": true,
  "prompt": "Please explain why a follow-up is required",
  "visible_if": {
    "all": [
      { "field": "start_date", "operator": "EXISTS" },
      { "field": "end_date", "operator": "EXISTS" },
      { "field": "end_date", "operator": "AFTER", "value_field": "start_date" }
    ]
  }
}
```

### Optional Field (Existence Check)

Show `handover_notes` only when both dates are filled (but the field itself is optional):

```json
{
  "id": "handover_notes",
  "type": "text",
  "required": false,
  "prompt": "Any handover notes for your team?",
  "visible_if": {
    "all": [
      { "field": "start_date", "operator": "EXISTS" },
      { "field": "end_date", "operator": "EXISTS" }
    ]
  }
}
```

## Full Example

See `backend/schemas/leave_request.json` and `backend/schemas/incident_report.json` for complete working examples.

"""
YAML frontmatter parser for hybrid form definitions.

Extracts the structured YAML header from a form markdown file.
The header contains field definitions, tools, and metadata that
the code can parse deterministically. The markdown body below
the header is passed to the LLM for rich conversational context.

Format:
    ---
    form_id: my_form
    title: My Form
    fields:
      - id: name
        type: text
        required: true
        prompt: "What is your name?"
    tools:
      - name: get_data
        purpose: "Fetch options"
    ---
    # My Form
    ... markdown body for the LLM ...
"""

import logging
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def parse_frontmatter(form_content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from a form definition string.

    Splits the content into a structured header dict and the
    remaining markdown body. If no frontmatter is found, returns
    an empty dict and the full content unchanged.

    Args:
        form_content: The full form definition (frontmatter + markdown).

    Returns:
        A tuple of (frontmatter_dict, markdown_body).
        frontmatter_dict is empty if no valid frontmatter is found.
    """
    stripped = form_content.strip()
    if not stripped.startswith("---"):
        return {}, form_content

    # Find the closing --- delimiter
    end_index = stripped.find("---", 3)
    if end_index == -1:
        return {}, form_content

    yaml_block = stripped[3:end_index].strip()
    markdown_body = stripped[end_index + 3:].strip()

    try:
        frontmatter = yaml.safe_load(yaml_block)
        if not isinstance(frontmatter, dict):
            logger.warning("Frontmatter is not a dict, ignoring")
            return {}, form_content
        return frontmatter, markdown_body
    except yaml.YAMLError as e:
        logger.warning("Failed to parse YAML frontmatter: %s", e)
        return {}, form_content


def extract_fields(frontmatter: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the fields list from parsed frontmatter.

    Args:
        frontmatter: Parsed frontmatter dict.

    Returns:
        List of field dicts, or empty list if not present.
    """
    fields = frontmatter.get("fields", [])
    return fields if isinstance(fields, list) else []


def extract_tools(frontmatter: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the tools list from parsed frontmatter.

    Args:
        frontmatter: Parsed frontmatter dict.

    Returns:
        List of tool dicts, or empty list if not present.
    """
    tools = frontmatter.get("tools", [])
    return tools if isinstance(tools, list) else []


def get_required_field_ids(frontmatter: dict[str, Any]) -> list[str]:
    """Get the IDs of all required fields from frontmatter.

    Fields with required=true or required="true" are included.
    Fields with required="conditional" are excluded (they depend
    on runtime conditions the LLM evaluates).

    Args:
        frontmatter: Parsed frontmatter dict.

    Returns:
        Ordered list of required field ID strings.
    """
    required = []
    for field in extract_fields(frontmatter):
        field_id = field.get("id", "")
        req = field.get("required", False)
        # Accept bool True or string "true" (not "conditional")
        if req is True or (isinstance(req, str) and req.lower() == "true"):
            if field_id:
                required.append(field_id)
    return required


def get_field_type_map(frontmatter: dict[str, Any]) -> dict[str, str]:
    """Build a field_id -> type mapping from frontmatter.

    Args:
        frontmatter: Parsed frontmatter dict.

    Returns:
        Dict like {"injuryDate": "date", "selectedEstablishment": "dropdown"}.
    """
    type_map = {}
    for field in extract_fields(frontmatter):
        field_id = field.get("id", "")
        field_type = field.get("type", "")
        if field_id and field_type:
            type_map[field_id] = field_type.lower()
    return type_map


def get_required_fields_by_step(frontmatter: dict[str, Any]) -> dict[int, list[str]]:
    """Group required field IDs by step number from frontmatter.

    Uses the field's ``step`` value when present. If missing/invalid,
    defaults to step 1.
    """
    by_step: dict[int, list[str]] = {}
    for field in extract_fields(frontmatter):
        field_id = field.get("id", "")
        req = field.get("required", False)
        is_required = req is True or (isinstance(req, str) and req.lower() == "true")
        if not field_id or not is_required:
            continue

        step_raw = field.get("step", 1)
        try:
            step_num = int(step_raw)
            if step_num < 1:
                step_num = 1
        except (TypeError, ValueError):
            step_num = 1

        by_step.setdefault(step_num, []).append(field_id)
    return by_step


def get_field_prompt_map(frontmatter: dict[str, Any]) -> dict[str, str]:
    """Build a field_id -> human prompt/label mapping from frontmatter."""
    prompt_map: dict[str, str] = {}
    for field in extract_fields(frontmatter):
        field_id = field.get("id", "")
        prompt = field.get("prompt", "")
        if field_id and isinstance(prompt, str) and prompt.strip():
            prompt_map[field_id] = prompt.strip()
    return prompt_map


def get_title(frontmatter: dict[str, Any]) -> str:
    """Get the form title from frontmatter.

    Args:
        frontmatter: Parsed frontmatter dict.

    Returns:
        Title string, or empty string if not present.
    """
    return frontmatter.get("title", "")

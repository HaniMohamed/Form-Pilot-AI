"""
Shared utility functions for the FormPilot AI backend.
"""

from datetime import date, datetime

from dateutil import parser as dateutil_parser


def parse_date(value: str) -> date | None:
    """Parse a date string into a date object.

    Supports ISO 8601 formats (YYYY-MM-DD) and datetime strings.
    Returns None if the value cannot be parsed.

    Args:
        value: The date string to parse.

    Returns:
        A date object, or None if parsing fails.
    """
    if not value or not isinstance(value, str):
        return None

    try:
        parsed = dateutil_parser.parse(value)
        # If the input is a datetime, extract just the date part
        if isinstance(parsed, datetime):
            return parsed.date()
        return parsed
    except (ValueError, TypeError, OverflowError):
        return None

"""
Deterministic visibility evaluator for form fields.

All visibility logic is evaluated in code — never by the LLM.
This module evaluates whether a field should be visible based on
its `visible_if` conditions and the current user answers.
"""

from backend.core.schema import ConditionOperator, FormField, VisibilityCondition
from backend.core.utils import parse_date


def is_field_visible(field: FormField, answers: dict) -> bool:
    """Determine if a field should be visible given the current answers.

    If the field has no `visible_if` rule, it is always visible.
    If it has a rule, all conditions in the `all` list must pass (AND logic).

    Args:
        field: The form field to evaluate.
        answers: Current user answers keyed by field ID.

    Returns:
        True if the field should be visible, False otherwise.
    """
    if field.visible_if is None:
        return True

    # AND logic: every condition must pass
    for condition in field.visible_if.all:
        if not _evaluate_condition(condition, answers):
            return False

    return True


def _evaluate_condition(condition: VisibilityCondition, answers: dict) -> bool:
    """Evaluate a single visibility condition against the current answers.

    Args:
        condition: The condition to evaluate.
        answers: Current user answers keyed by field ID.

    Returns:
        True if the condition passes, False otherwise.
    """
    field_value = answers.get(condition.field)

    match condition.operator:
        case ConditionOperator.EXISTS:
            return field_value is not None

        case ConditionOperator.EQUALS:
            compare_value = _get_compare_value(condition, answers)
            if field_value is None or compare_value is None:
                return False
            return str(field_value) == str(compare_value)

        case ConditionOperator.NOT_EQUALS:
            compare_value = _get_compare_value(condition, answers)
            if field_value is None or compare_value is None:
                return False
            return str(field_value) != str(compare_value)

        case ConditionOperator.AFTER:
            return _compare_dates(field_value, condition, answers, lambda a, b: a > b)

        case ConditionOperator.BEFORE:
            return _compare_dates(field_value, condition, answers, lambda a, b: a < b)

        case ConditionOperator.ON_OR_AFTER:
            return _compare_dates(field_value, condition, answers, lambda a, b: a >= b)

        case ConditionOperator.ON_OR_BEFORE:
            return _compare_dates(field_value, condition, answers, lambda a, b: a <= b)

    # Unknown operator — should not happen due to enum validation
    return False


def _get_compare_value(condition: VisibilityCondition, answers: dict) -> str | None:
    """Get the comparison value from either a static value or a dynamic field reference.

    Args:
        condition: The condition containing value or value_field.
        answers: Current user answers keyed by field ID.

    Returns:
        The comparison value as a string, or None if unavailable.
    """
    # Dynamic reference takes precedence if both are somehow set
    if condition.value_field is not None:
        val = answers.get(condition.value_field)
        return str(val) if val is not None else None

    return condition.value


def _compare_dates(
    field_value: str | None,
    condition: VisibilityCondition,
    answers: dict,
    comparator,
) -> bool:
    """Compare two date values using the given comparator function.

    Args:
        field_value: The raw field value from answers.
        condition: The condition (used to resolve the compare value).
        answers: Current user answers keyed by field ID.
        comparator: A function (date, date) -> bool for the comparison.

    Returns:
        True if the date comparison passes, False otherwise.
    """
    if field_value is None:
        return False

    compare_raw = _get_compare_value(condition, answers)
    if compare_raw is None:
        return False

    field_date = parse_date(str(field_value))
    compare_date = parse_date(str(compare_raw))

    if field_date is None or compare_date is None:
        return False

    return comparator(field_date, compare_date)

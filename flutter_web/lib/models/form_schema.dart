/// Dart models for FormSchema, FormField, and VisibilityCondition.
///
/// Mirrors the Python backend Pydantic models in backend/core/schema.py.
/// Supports fromJson/toJson serialization for API communication.
library;

/// Supported form field types.
enum FieldType {
  dropdown,
  checkbox,
  text,
  date,
  datetime,
  location;

  static FieldType fromString(String value) {
    return FieldType.values.firstWhere(
      (e) => e.name == value,
      orElse: () => throw ArgumentError('Unknown FieldType: $value'),
    );
  }
}

/// Supported visibility condition operators.
enum ConditionOperator {
  exists('EXISTS'),
  equals('EQUALS'),
  notEquals('NOT_EQUALS'),
  after('AFTER'),
  before('BEFORE'),
  onOrAfter('ON_OR_AFTER'),
  onOrBefore('ON_OR_BEFORE');

  final String value;
  const ConditionOperator(this.value);

  static ConditionOperator fromString(String value) {
    return ConditionOperator.values.firstWhere(
      (e) => e.value == value,
      orElse: () => throw ArgumentError('Unknown ConditionOperator: $value'),
    );
  }
}

/// A single visibility condition (e.g., field X must EQUAL "Sick").
class VisibilityCondition {
  final String field;
  final ConditionOperator operator;
  final String? value;
  final String? valueField;

  const VisibilityCondition({
    required this.field,
    required this.operator,
    this.value,
    this.valueField,
  });

  factory VisibilityCondition.fromJson(Map<String, dynamic> json) {
    return VisibilityCondition(
      field: json['field'] as String,
      operator: ConditionOperator.fromString(json['operator'] as String),
      value: json['value'] as String?,
      valueField: json['value_field'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'field': field,
      'operator': operator.value,
      if (value != null) 'value': value,
      if (valueField != null) 'value_field': valueField,
    };
  }
}

/// Visibility rule — all conditions must be met (AND logic).
class VisibilityRule {
  final List<VisibilityCondition> all;

  const VisibilityRule({required this.all});

  factory VisibilityRule.fromJson(Map<String, dynamic> json) {
    final allList = (json['all'] as List<dynamic>)
        .map((e) => VisibilityCondition.fromJson(e as Map<String, dynamic>))
        .toList();
    return VisibilityRule(all: allList);
  }

  Map<String, dynamic> toJson() {
    return {
      'all': all.map((c) => c.toJson()).toList(),
    };
  }
}

/// A single form field definition.
class FormField {
  final String id;
  final FieldType type;
  final bool required;
  final String prompt;
  final List<String>? options;
  final VisibilityRule? visibleIf;

  const FormField({
    required this.id,
    required this.type,
    required this.required,
    required this.prompt,
    this.options,
    this.visibleIf,
  });

  factory FormField.fromJson(Map<String, dynamic> json) {
    return FormField(
      id: json['id'] as String,
      type: FieldType.fromString(json['type'] as String),
      required: json['required'] as bool? ?? true,
      prompt: json['prompt'] as String,
      options: (json['options'] as List<dynamic>?)
          ?.map((e) => e as String)
          .toList(),
      visibleIf: json['visible_if'] != null
          ? VisibilityRule.fromJson(json['visible_if'] as Map<String, dynamic>)
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'type': type.name,
      'required': required,
      'prompt': prompt,
      if (options != null) 'options': options,
      if (visibleIf != null) 'visible_if': visibleIf!.toJson(),
    };
  }
}

/// Interaction rules for the form.
class InteractionRules {
  final bool askOneFieldAtATime;
  final bool neverAssumeValues;

  const InteractionRules({
    this.askOneFieldAtATime = true,
    this.neverAssumeValues = true,
  });

  factory InteractionRules.fromJson(Map<String, dynamic> json) {
    final interaction = json['interaction'] as Map<String, dynamic>? ?? {};
    return InteractionRules(
      askOneFieldAtATime:
          interaction['ask_one_field_at_a_time'] as bool? ?? true,
      neverAssumeValues:
          interaction['never_assume_values'] as bool? ?? true,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'interaction': {
        'ask_one_field_at_a_time': askOneFieldAtATime,
        'never_assume_values': neverAssumeValues,
      },
    };
  }
}

/// The top-level form schema definition.
class FormSchema {
  final String formId;
  final InteractionRules? rules;
  final List<FormField> fields;

  const FormSchema({
    required this.formId,
    this.rules,
    required this.fields,
  });

  factory FormSchema.fromJson(Map<String, dynamic> json) {
    return FormSchema(
      formId: json['form_id'] as String,
      rules: json['rules'] != null
          ? InteractionRules.fromJson(json['rules'] as Map<String, dynamic>)
          : null,
      fields: (json['fields'] as List<dynamic>)
          .map((e) => FormField.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'form_id': formId,
      if (rules != null) 'rules': rules!.toJson(),
      'fields': fields.map((f) => f.toJson()).toList(),
    };
  }
}

/// Dart models for AI action types returned by the backend.
///
/// Mirrors the Python backend action protocol in backend/core/actions.py.
/// Each action type maps to a specific UI widget to render.
library;

/// All supported AI action types.
enum ActionType {
  askDropdown('ASK_DROPDOWN'),
  askCheckbox('ASK_CHECKBOX'),
  askText('ASK_TEXT'),
  askDate('ASK_DATE'),
  askDatetime('ASK_DATETIME'),
  askLocation('ASK_LOCATION'),
  toolCall('TOOL_CALL'),
  formComplete('FORM_COMPLETE'),
  message('MESSAGE');

  final String value;
  const ActionType(this.value);

  static ActionType fromString(String value) {
    return ActionType.values.firstWhere(
      (e) => e.value == value,
      orElse: () => throw ArgumentError('Unknown ActionType: $value'),
    );
  }
}

/// A parsed AI action from the backend response.
///
/// Wraps the raw JSON and provides typed accessors for the common fields.
class AIAction {
  final ActionType type;
  final Map<String, dynamic> raw;

  const AIAction({required this.type, required this.raw});

  factory AIAction.fromJson(Map<String, dynamic> json) {
    final actionStr = json['action'] as String;
    return AIAction(
      type: ActionType.fromString(actionStr),
      raw: json,
    );
  }

  /// The field ID this action targets (for ASK_* actions).
  String? get fieldId => raw['field_id'] as String?;

  /// The label/prompt text (for ASK_* actions).
  String? get label => raw['label'] as String?;

  /// The message text (for MESSAGE actions and ASK_* with message).
  String? get message => raw['message'] as String?;

  /// The text content (for MESSAGE actions).
  String? get text => raw['text'] as String?;

  /// The options list (for ASK_DROPDOWN and ASK_CHECKBOX).
  List<String>? get options {
    final opts = raw['options'] as List<dynamic>?;
    return opts?.map((e) => e.toString()).toList();
  }

  /// The final data payload (for FORM_COMPLETE).
  Map<String, dynamic>? get data {
    return raw['data'] as Map<String, dynamic>?;
  }

  /// The tool name (for TOOL_CALL actions).
  String? get toolName => raw['tool_name'] as String?;

  /// The tool arguments (for TOOL_CALL actions).
  Map<String, dynamic>? get toolArgs {
    final args = raw['tool_args'];
    if (args is Map<String, dynamic>) return args;
    return null;
  }

  /// Whether this is an ASK_* action (field question).
  bool get isFieldAction =>
      type != ActionType.formComplete &&
      type != ActionType.message &&
      type != ActionType.toolCall;

  /// Whether this is the form completion action.
  bool get isFormComplete => type == ActionType.formComplete;

  /// Whether this is a plain message action.
  bool get isMessage => type == ActionType.message;

  /// Whether this is a tool call action.
  bool get isToolCall => type == ActionType.toolCall;

  Map<String, dynamic> toJson() => raw;
}

/// The full response from the /chat endpoint.
class ChatResponse {
  final AIAction action;
  final String conversationId;
  final Map<String, dynamic> answers;

  const ChatResponse({
    required this.action,
    required this.conversationId,
    required this.answers,
  });

  factory ChatResponse.fromJson(Map<String, dynamic> json) {
    return ChatResponse(
      action: AIAction.fromJson(json['action'] as Map<String, dynamic>),
      conversationId: json['conversation_id'] as String,
      answers: Map<String, dynamic>.from(
        json['answers'] as Map<String, dynamic>,
      ),
    );
  }
}

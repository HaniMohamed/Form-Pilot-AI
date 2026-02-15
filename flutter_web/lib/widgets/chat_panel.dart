/// Chat panel widget — displays conversation messages and inline action widgets.
///
/// When the AI returns an ASK_* action, the appropriate widget (dropdown,
/// date picker, checkboxes, etc.) is rendered above the text input.
/// Users can always type in the text field as an alternative.
library;

import 'dart:convert';

import 'package:flutter/material.dart';

import '../models/ai_action.dart';
import '../screens/simulation_screen.dart';

/// The chat panel showing messages, inline action widgets, and text input.
class ChatPanel extends StatefulWidget {
  final List<ChatMessage> messages;
  final bool isLoading;
  final ValueChanged<String> onSendMessage;
  final bool isSessionActive;

  /// The current AI action — drives which inline widget to show.
  final AIAction? currentAction;

  const ChatPanel({
    super.key,
    required this.messages,
    required this.isLoading,
    required this.onSendMessage,
    required this.isSessionActive,
    this.currentAction,
  });

  @override
  State<ChatPanel> createState() => _ChatPanelState();
}

class _ChatPanelState extends State<ChatPanel> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void didUpdateWidget(ChatPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Auto-scroll to bottom when new messages arrive
    if (widget.messages.length > oldWidget.messages.length) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToBottom();
      });
    }
  }

  void _scrollToBottom() {
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    }
  }

  void _handleSend() {
    final text = _controller.text.trim();
    if (text.isEmpty || widget.isLoading) return;
    _controller.clear();
    widget.onSendMessage(text);
  }

  /// Called when a widget (dropdown, date picker, etc.) submits a value.
  void _handleWidgetSubmit(String value) {
    if (widget.isLoading) return;
    widget.onSendMessage(value);
  }

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Column(
      children: [
        // Header
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: colorScheme.surfaceContainerLow,
            border: Border(
              bottom: BorderSide(color: colorScheme.outlineVariant),
            ),
          ),
          child: Row(
            children: [
              Icon(Icons.chat_bubble_outline, size: 18, color: colorScheme.primary),
              const SizedBox(width: 8),
              Text(
                'Chat',
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: colorScheme.onSurface,
                ),
              ),
            ],
          ),
        ),

        // Messages list
        Expanded(
          child: widget.messages.isEmpty
              ? _buildEmptyState(colorScheme)
              : ListView.builder(
                  controller: _scrollController,
                  padding: const EdgeInsets.all(12),
                  itemCount: widget.messages.length + (widget.isLoading ? 1 : 0),
                  itemBuilder: (context, index) {
                    if (index == widget.messages.length) {
                      return _buildTypingIndicator(colorScheme);
                    }
                    return _buildMessageBubble(widget.messages[index], colorScheme);
                  },
                ),
        ),

        // Inline action widget (shown above the text input when action is active)
        if (_shouldShowInlineWidget) _buildInlineActionWidget(colorScheme),

        // Text input area (always visible, disabled when form is complete)
        _buildTextInput(colorScheme),
      ],
    );
  }

  /// Whether to show an inline action widget above the text input.
  bool get _shouldShowInlineWidget {
    final action = widget.currentAction;
    if (action == null || widget.isLoading) return false;
    // Show inline widgets for field-specific actions (not MESSAGE, FORM_COMPLETE, or TOOL_CALL)
    return action.isFieldAction && action.type != ActionType.askText;
  }

  /// Build the inline action widget based on the current action type.
  Widget _buildInlineActionWidget(ColorScheme colorScheme) {
    final action = widget.currentAction!;

    return Container(
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
        border: Border(
          top: BorderSide(color: colorScheme.outlineVariant),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Field label
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 0),
            child: Row(
              children: [
                Icon(_iconForAction(action.type), size: 16, color: colorScheme.primary),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    action.label ?? '',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: colorScheme.primary,
                    ),
                  ),
                ),
              ],
            ),
          ),
          // The actual widget
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 8, 14, 10),
            child: switch (action.type) {
              ActionType.askDropdown => _InlineDropdown(
                  options: action.options ?? [],
                  onSubmit: _handleWidgetSubmit,
                ),
              ActionType.askCheckbox => _InlineCheckbox(
                  options: action.options ?? [],
                  onSubmit: _handleWidgetSubmit,
                ),
              ActionType.askDate => _InlineDatePicker(
                  onSubmit: _handleWidgetSubmit,
                ),
              ActionType.askDatetime => _InlineDateTimePicker(
                  onSubmit: _handleWidgetSubmit,
                ),
              ActionType.askLocation => _InlineLocation(
                  onSubmit: _handleWidgetSubmit,
                ),
              _ => const SizedBox.shrink(),
            },
          ),
        ],
      ),
    );
  }

  IconData _iconForAction(ActionType type) {
    return switch (type) {
      ActionType.askDropdown => Icons.arrow_drop_down_circle_outlined,
      ActionType.askCheckbox => Icons.check_box_outlined,
      ActionType.askDate => Icons.calendar_today,
      ActionType.askDatetime => Icons.event,
      ActionType.askLocation => Icons.location_on_outlined,
      ActionType.askText => Icons.text_fields,
      _ => Icons.widgets_outlined,
    };
  }

  Widget _buildTextInput(ColorScheme colorScheme) {
    final isComplete = widget.currentAction?.isFormComplete == true;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerLow,
        border: Border(
          top: BorderSide(color: colorScheme.outlineVariant),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _controller,
              enabled: widget.isSessionActive && !widget.isLoading && !isComplete,
              decoration: InputDecoration(
                hintText: _inputHintText,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                ),
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 10,
                ),
                isDense: true,
              ),
              onSubmitted: (_) => _handleSend(),
              textInputAction: TextInputAction.send,
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(
            onPressed:
                (widget.isSessionActive && !widget.isLoading && !isComplete)
                    ? _handleSend
                    : null,
            icon: const Icon(Icons.send, size: 18),
          ),
        ],
      ),
    );
  }

  String get _inputHintText {
    if (!widget.isSessionActive) return 'Select a schema to start';
    if (widget.currentAction?.isFormComplete == true) return 'Form completed';
    if (widget.currentAction?.type == ActionType.askText) {
      return widget.currentAction?.label ?? 'Type your response...';
    }
    if (_shouldShowInlineWidget) return 'Or type your response...';
    return 'Type your response...';
  }

  Widget _buildEmptyState(ColorScheme colorScheme) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.forum_outlined, size: 48, color: colorScheme.outline),
          const SizedBox(height: 12),
          Text(
            'Conversation will appear here',
            style: TextStyle(color: colorScheme.outline),
          ),
        ],
      ),
    );
  }

  Widget _buildMessageBubble(ChatMessage message, ColorScheme colorScheme) {
    final isUser = message.isUser;

    // Check if this is a form-complete message
    if (!isUser && message.formCompleteData != null) {
      return _buildFormCompleteCard(message, colorScheme);
    }

    // Check if this is a tool-call status message
    if (!isUser && message.isToolCall) {
      return _buildToolCallBubble(message, colorScheme);
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        mainAxisAlignment:
            isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isUser) ...[
            CircleAvatar(
              radius: 14,
              backgroundColor: colorScheme.primaryContainer,
              child: Icon(
                Icons.smart_toy,
                size: 16,
                color: colorScheme.onPrimaryContainer,
              ),
            ),
            const SizedBox(width: 8),
          ],
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: isUser
                    ? colorScheme.primaryContainer
                    : colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(16),
                  topRight: const Radius.circular(16),
                  bottomLeft: Radius.circular(isUser ? 16 : 4),
                  bottomRight: Radius.circular(isUser ? 4 : 16),
                ),
              ),
              child: Text(
                message.text,
                style: TextStyle(
                  color: isUser
                      ? colorScheme.onPrimaryContainer
                      : colorScheme.onSurface,
                  fontSize: 14,
                ),
              ),
            ),
          ),
          if (isUser) ...[
            const SizedBox(width: 8),
            CircleAvatar(
              radius: 14,
              backgroundColor: colorScheme.tertiaryContainer,
              child: Icon(
                Icons.person,
                size: 16,
                color: colorScheme.onTertiaryContainer,
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// Renders a TOOL_CALL status message with a distinct style.
  Widget _buildToolCallBubble(ChatMessage message, ColorScheme colorScheme) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CircleAvatar(
            radius: 14,
            backgroundColor: Colors.blue.shade100,
            child: Icon(
              Icons.build_circle,
              size: 16,
              color: Colors.blue.shade700,
            ),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: Colors.blue.shade50,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(16),
                  topRight: Radius.circular(16),
                  bottomRight: Radius.circular(16),
                  bottomLeft: Radius.circular(4),
                ),
                border: Border.all(color: Colors.blue.shade200),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.blue.shade600,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      message.text,
                      style: TextStyle(
                        color: Colors.blue.shade900,
                        fontSize: 13,
                        fontStyle: FontStyle.italic,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// Renders FORM_COMPLETE data as a rich card in the chat.
  Widget _buildFormCompleteCard(ChatMessage message, ColorScheme colorScheme) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CircleAvatar(
            radius: 14,
            backgroundColor: Colors.green.shade100,
            child: Icon(
              Icons.check_circle,
              size: 16,
              color: Colors.green.shade700,
            ),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Card(
              elevation: 0,
              margin: EdgeInsets.zero,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
                side: BorderSide(color: Colors.green.shade300),
              ),
              color: Colors.green.shade50,
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.check_circle, color: Colors.green.shade700, size: 20),
                        const SizedBox(width: 6),
                        Text(
                          'Form Complete!',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Colors.green.shade700,
                            fontSize: 15,
                          ),
                        ),
                      ],
                    ),
                    if (message.text.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text(
                        message.text,
                        style: TextStyle(
                          color: Colors.green.shade900,
                          fontSize: 13,
                        ),
                      ),
                    ],
                    const SizedBox(height: 10),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.green.shade200),
                      ),
                      child: SelectableText(
                        const JsonEncoder.withIndent('  ')
                            .convert(message.formCompleteData),
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 12,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTypingIndicator(ColorScheme colorScheme) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          CircleAvatar(
            radius: 14,
            backgroundColor: colorScheme.primaryContainer,
            child: Icon(
              Icons.smart_toy,
              size: 16,
              color: colorScheme.onPrimaryContainer,
            ),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: colorScheme.surfaceContainerHighest,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(16),
                topRight: Radius.circular(16),
                bottomRight: Radius.circular(16),
                bottomLeft: Radius.circular(4),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: colorScheme.primary,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  'Thinking...',
                  style: TextStyle(
                    color: colorScheme.outline,
                    fontSize: 13,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Inline action widgets — compact versions for the chat input area
// ─────────────────────────────────────────────────────────────────────────────

/// Compact inline dropdown selector.
class _InlineDropdown extends StatefulWidget {
  final List<String> options;
  final ValueChanged<String> onSubmit;

  const _InlineDropdown({required this.options, required this.onSubmit});

  @override
  State<_InlineDropdown> createState() => _InlineDropdownState();
}

class _InlineDropdownState extends State<_InlineDropdown> {
  String? _selected;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: DropdownButtonFormField<String>(
            initialValue: _selected,
            decoration: InputDecoration(
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              isDense: true,
            ),
            hint: const Text('Choose...'),
            items: widget.options
                .map((opt) => DropdownMenuItem(value: opt, child: Text(opt)))
                .toList(),
            onChanged: (val) => setState(() => _selected = val),
          ),
        ),
        const SizedBox(width: 8),
        FilledButton(
          onPressed: _selected != null ? () => widget.onSubmit(_selected!) : null,
          child: const Text('Submit'),
        ),
      ],
    );
  }
}

/// Compact inline checkbox group.
class _InlineCheckbox extends StatefulWidget {
  final List<String> options;
  final ValueChanged<String> onSubmit;

  const _InlineCheckbox({required this.options, required this.onSubmit});

  @override
  State<_InlineCheckbox> createState() => _InlineCheckboxState();
}

class _InlineCheckboxState extends State<_InlineCheckbox> {
  final Set<String> _selected = {};

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: widget.options.map((opt) {
            final isSelected = _selected.contains(opt);
            return FilterChip(
              label: Text(opt),
              selected: isSelected,
              onSelected: (checked) {
                setState(() {
                  if (checked) {
                    _selected.add(opt);
                  } else {
                    _selected.remove(opt);
                  }
                });
              },
            );
          }).toList(),
        ),
        const SizedBox(height: 8),
        Align(
          alignment: Alignment.centerRight,
          child: FilledButton(
            onPressed: _selected.isNotEmpty
                ? () => widget.onSubmit(_selected.join(', '))
                : null,
            child: const Text('Submit'),
          ),
        ),
      ],
    );
  }
}

/// Compact inline date picker.
class _InlineDatePicker extends StatefulWidget {
  final ValueChanged<String> onSubmit;

  const _InlineDatePicker({required this.onSubmit});

  @override
  State<_InlineDatePicker> createState() => _InlineDatePickerState();
}

class _InlineDatePickerState extends State<_InlineDatePicker> {
  DateTime? _selectedDate;

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: now,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _selectedDate = picked);
  }

  String get _formatted {
    if (_selectedDate == null) return '';
    final d = _selectedDate!;
    return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: _pickDate,
            icon: const Icon(Icons.calendar_today, size: 16),
            label: Text(_selectedDate != null ? _formatted : 'Pick a date'),
          ),
        ),
        const SizedBox(width: 8),
        FilledButton(
          onPressed: _selectedDate != null ? () => widget.onSubmit(_formatted) : null,
          child: const Text('Submit'),
        ),
      ],
    );
  }
}

/// Compact inline date + time picker.
class _InlineDateTimePicker extends StatefulWidget {
  final ValueChanged<String> onSubmit;

  const _InlineDateTimePicker({required this.onSubmit});

  @override
  State<_InlineDateTimePicker> createState() => _InlineDateTimePickerState();
}

class _InlineDateTimePickerState extends State<_InlineDateTimePicker> {
  DateTime? _selectedDate;
  TimeOfDay? _selectedTime;

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: now,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _selectedDate = picked);
  }

  Future<void> _pickTime() async {
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.now(),
    );
    if (picked != null) setState(() => _selectedTime = picked);
  }

  String get _formatted {
    if (_selectedDate == null) return '';
    final d = _selectedDate!;
    final datePart =
        '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
    if (_selectedTime == null) return datePart;
    final timePart =
        '${_selectedTime!.hour.toString().padLeft(2, '0')}:${_selectedTime!.minute.toString().padLeft(2, '0')}';
    return '$datePart $timePart';
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: _pickDate,
            icon: const Icon(Icons.calendar_today, size: 16),
            label: Text(
              _selectedDate != null
                  ? '${_selectedDate!.year}-${_selectedDate!.month.toString().padLeft(2, '0')}-${_selectedDate!.day.toString().padLeft(2, '0')}'
                  : 'Date',
            ),
          ),
        ),
        const SizedBox(width: 6),
        Expanded(
          child: OutlinedButton.icon(
            onPressed: _pickTime,
            icon: const Icon(Icons.access_time, size: 16),
            label: Text(
              _selectedTime != null
                  ? '${_selectedTime!.hour.toString().padLeft(2, '0')}:${_selectedTime!.minute.toString().padLeft(2, '0')}'
                  : 'Time',
            ),
          ),
        ),
        const SizedBox(width: 8),
        FilledButton(
          onPressed: _selectedDate != null ? () => widget.onSubmit(_formatted) : null,
          child: const Text('Submit'),
        ),
      ],
    );
  }
}

/// Compact inline location input (lat/lng).
class _InlineLocation extends StatefulWidget {
  final ValueChanged<String> onSubmit;

  const _InlineLocation({required this.onSubmit});

  @override
  State<_InlineLocation> createState() => _InlineLocationState();
}

class _InlineLocationState extends State<_InlineLocation> {
  final _latController = TextEditingController();
  final _lngController = TextEditingController();

  @override
  void dispose() {
    _latController.dispose();
    _lngController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: TextField(
            controller: _latController,
            decoration: InputDecoration(
              labelText: 'Lat',
              hintText: '24.7136',
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
              isDense: true,
              contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
            ),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
          ),
        ),
        const SizedBox(width: 6),
        Expanded(
          child: TextField(
            controller: _lngController,
            decoration: InputDecoration(
              labelText: 'Lng',
              hintText: '46.6753',
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
              isDense: true,
              contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
            ),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
          ),
        ),
        const SizedBox(width: 8),
        FilledButton(
          onPressed: () {
            final lat = _latController.text.trim();
            final lng = _lngController.text.trim();
            if (lat.isNotEmpty && lng.isNotEmpty) {
              widget.onSubmit('$lat, $lng');
            }
          },
          child: const Text('Submit'),
        ),
      ],
    );
  }
}

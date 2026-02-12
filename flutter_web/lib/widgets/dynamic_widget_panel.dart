/// Dynamic widget panel — renders the appropriate UI widget based on AI action.
///
/// Maps each action type to a Flutter widget:
/// - ASK_DROPDOWN → DropdownButton
/// - ASK_CHECKBOX → CheckboxListTile group
/// - ASK_TEXT → TextField
/// - ASK_DATE → Date picker
/// - ASK_DATETIME → Date + time picker
/// - ASK_LOCATION → Lat/lng text inputs
/// - FORM_COMPLETE → Final data display
/// - MESSAGE → Informational message
library;

import 'dart:convert';

import 'package:flutter/material.dart';

import '../models/ai_action.dart';

/// Renders a dynamic UI widget based on the current AI action.
class DynamicWidgetPanel extends StatelessWidget {
  final AIAction? action;
  final bool isLoading;
  final String? errorMessage;
  final ValueChanged<String> onSubmit;

  const DynamicWidgetPanel({
    super.key,
    required this.action,
    required this.isLoading,
    this.errorMessage,
    required this.onSubmit,
  });

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
              Icon(Icons.widgets_outlined, size: 18, color: colorScheme.primary),
              const SizedBox(width: 8),
              Text(
                'Form Widget',
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: colorScheme.onSurface,
                ),
              ),
              if (action?.fieldId != null) ...[
                const SizedBox(width: 12),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: colorScheme.primaryContainer,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    action!.fieldId!,
                    style: TextStyle(
                      fontSize: 12,
                      fontFamily: 'monospace',
                      color: colorScheme.onPrimaryContainer,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),

        // Content
        Expanded(
          child: _buildContent(context, colorScheme),
        ),
      ],
    );
  }

  Widget _buildContent(BuildContext context, ColorScheme colorScheme) {
    if (errorMessage != null) {
      return _buildError(colorScheme);
    }

    if (isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (action == null) {
      return _buildEmptyState(colorScheme);
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 500),
          child: _buildWidgetForAction(context, colorScheme),
        ),
      ),
    );
  }

  Widget _buildEmptyState(ColorScheme colorScheme) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.touch_app_outlined, size: 48, color: colorScheme.outline),
          const SizedBox(height: 12),
          Text(
            'Waiting for conversation to start',
            style: TextStyle(color: colorScheme.outline),
          ),
        ],
      ),
    );
  }

  Widget _buildError(ColorScheme colorScheme) {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(16),
        margin: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: colorScheme.errorContainer,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 32, color: colorScheme.error),
            const SizedBox(height: 8),
            Text(
              errorMessage!,
              textAlign: TextAlign.center,
              style: TextStyle(color: colorScheme.onErrorContainer),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildWidgetForAction(BuildContext context, ColorScheme colorScheme) {
    return switch (action!.type) {
      ActionType.askDropdown => _DropdownWidget(
          action: action!,
          onSubmit: onSubmit,
        ),
      ActionType.askCheckbox => _CheckboxWidget(
          action: action!,
          onSubmit: onSubmit,
        ),
      ActionType.askText => _TextInputWidget(
          action: action!,
          onSubmit: onSubmit,
        ),
      ActionType.askDate => _DatePickerWidget(
          action: action!,
          onSubmit: onSubmit,
        ),
      ActionType.askDatetime => _DateTimePickerWidget(
          action: action!,
          onSubmit: onSubmit,
        ),
      ActionType.askLocation => _LocationWidget(
          action: action!,
          onSubmit: onSubmit,
        ),
      ActionType.formComplete => _FormCompleteWidget(
          action: action!,
          colorScheme: colorScheme,
        ),
      ActionType.message => _MessageWidget(
          action: action!,
          colorScheme: colorScheme,
        ),
    };
  }
}

// --- Individual action widgets ---

/// Dropdown selector widget.
class _DropdownWidget extends StatefulWidget {
  final AIAction action;
  final ValueChanged<String> onSubmit;

  const _DropdownWidget({required this.action, required this.onSubmit});

  @override
  State<_DropdownWidget> createState() => _DropdownWidgetState();
}

class _DropdownWidgetState extends State<_DropdownWidget> {
  String? _selected;

  @override
  Widget build(BuildContext context) {
    final options = widget.action.options ?? [];

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.action.label ?? 'Select an option',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              initialValue: _selected,
              decoration: InputDecoration(
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 12,
                ),
              ),
              hint: const Text('Choose...'),
              items: options
                  .map((opt) => DropdownMenuItem(value: opt, child: Text(opt)))
                  .toList(),
              onChanged: (val) => setState(() => _selected = val),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _selected != null
                  ? () => widget.onSubmit(_selected!)
                  : null,
              child: const Text('Submit'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Checkbox group widget.
class _CheckboxWidget extends StatefulWidget {
  final AIAction action;
  final ValueChanged<String> onSubmit;

  const _CheckboxWidget({required this.action, required this.onSubmit});

  @override
  State<_CheckboxWidget> createState() => _CheckboxWidgetState();
}

class _CheckboxWidgetState extends State<_CheckboxWidget> {
  final Set<String> _selected = {};

  @override
  Widget build(BuildContext context) {
    final options = widget.action.options ?? [];

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.action.label ?? 'Select options',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            ...options.map((opt) => CheckboxListTile(
                  title: Text(opt),
                  value: _selected.contains(opt),
                  onChanged: (checked) {
                    setState(() {
                      if (checked == true) {
                        _selected.add(opt);
                      } else {
                        _selected.remove(opt);
                      }
                    });
                  },
                  controlAffinity: ListTileControlAffinity.leading,
                  dense: true,
                )),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _selected.isNotEmpty
                  ? () => widget.onSubmit(_selected.join(', '))
                  : null,
              child: const Text('Submit'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Text input widget.
class _TextInputWidget extends StatefulWidget {
  final AIAction action;
  final ValueChanged<String> onSubmit;

  const _TextInputWidget({required this.action, required this.onSubmit});

  @override
  State<_TextInputWidget> createState() => _TextInputWidgetState();
}

class _TextInputWidgetState extends State<_TextInputWidget> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.action.label ?? 'Enter text',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _controller,
              decoration: InputDecoration(
                hintText: 'Type here...',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
              maxLines: 3,
              onSubmitted: (val) {
                if (val.trim().isNotEmpty) widget.onSubmit(val.trim());
              },
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: () {
                final text = _controller.text.trim();
                if (text.isNotEmpty) widget.onSubmit(text);
              },
              child: const Text('Submit'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Date picker widget.
class _DatePickerWidget extends StatefulWidget {
  final AIAction action;
  final ValueChanged<String> onSubmit;

  const _DatePickerWidget({required this.action, required this.onSubmit});

  @override
  State<_DatePickerWidget> createState() => _DatePickerWidgetState();
}

class _DatePickerWidgetState extends State<_DatePickerWidget> {
  DateTime? _selectedDate;

  Future<void> _pickDate(BuildContext context) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: now,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) {
      setState(() => _selectedDate = picked);
    }
  }

  String get _formattedDate {
    if (_selectedDate == null) return '';
    return '${_selectedDate!.year}-${_selectedDate!.month.toString().padLeft(2, '0')}-${_selectedDate!.day.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.action.label ?? 'Select a date',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: () => _pickDate(context),
              icon: const Icon(Icons.calendar_today),
              label: Text(
                _selectedDate != null ? _formattedDate : 'Pick a date',
              ),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _selectedDate != null
                  ? () => widget.onSubmit(_formattedDate)
                  : null,
              child: const Text('Submit'),
            ),
          ],
        ),
      ),
    );
  }
}

/// DateTime picker widget (date + time).
class _DateTimePickerWidget extends StatefulWidget {
  final AIAction action;
  final ValueChanged<String> onSubmit;

  const _DateTimePickerWidget({required this.action, required this.onSubmit});

  @override
  State<_DateTimePickerWidget> createState() => _DateTimePickerWidgetState();
}

class _DateTimePickerWidgetState extends State<_DateTimePickerWidget> {
  DateTime? _selectedDate;
  TimeOfDay? _selectedTime;

  Future<void> _pickDate(BuildContext context) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: now,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) {
      setState(() => _selectedDate = picked);
    }
  }

  Future<void> _pickTime(BuildContext context) async {
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.now(),
    );
    if (picked != null) {
      setState(() => _selectedTime = picked);
    }
  }

  String get _formattedDateTime {
    if (_selectedDate == null) return '';
    final datePart =
        '${_selectedDate!.year}-${_selectedDate!.month.toString().padLeft(2, '0')}-${_selectedDate!.day.toString().padLeft(2, '0')}';
    if (_selectedTime == null) return datePart;
    final timePart =
        '${_selectedTime!.hour.toString().padLeft(2, '0')}:${_selectedTime!.minute.toString().padLeft(2, '0')}';
    return '$datePart $timePart';
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.action.label ?? 'Select date and time',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => _pickDate(context),
                    icon: const Icon(Icons.calendar_today),
                    label: Text(
                      _selectedDate != null
                          ? '${_selectedDate!.year}-${_selectedDate!.month.toString().padLeft(2, '0')}-${_selectedDate!.day.toString().padLeft(2, '0')}'
                          : 'Date',
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => _pickTime(context),
                    icon: const Icon(Icons.access_time),
                    label: Text(
                      _selectedTime != null
                          ? '${_selectedTime!.hour.toString().padLeft(2, '0')}:${_selectedTime!.minute.toString().padLeft(2, '0')}'
                          : 'Time',
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _selectedDate != null
                  ? () => widget.onSubmit(_formattedDateTime)
                  : null,
              child: const Text('Submit'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Location input widget (lat/lng text fields for simulation).
class _LocationWidget extends StatefulWidget {
  final AIAction action;
  final ValueChanged<String> onSubmit;

  const _LocationWidget({required this.action, required this.onSubmit});

  @override
  State<_LocationWidget> createState() => _LocationWidgetState();
}

class _LocationWidgetState extends State<_LocationWidget> {
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
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.action.label ?? 'Enter location',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _latController,
                    decoration: InputDecoration(
                      labelText: 'Latitude',
                      hintText: '24.7136',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _lngController,
                    decoration: InputDecoration(
                      labelText: 'Longitude',
                      hintText: '46.6753',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
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
        ),
      ),
    );
  }
}

/// Form complete widget — shows the final data payload.
class _FormCompleteWidget extends StatelessWidget {
  final AIAction action;
  final ColorScheme colorScheme;

  const _FormCompleteWidget({
    required this.action,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context) {
    final data = action.data ?? {};

    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Colors.green.shade300),
      ),
      color: Colors.green.shade50,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(Icons.check_circle, color: Colors.green.shade700, size: 28),
                const SizedBox(width: 8),
                Text(
                  'Form Complete!',
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        color: Colors.green.shade700,
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            const Text(
              'Final Data Payload:',
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.green.shade200),
              ),
              child: SelectableText(
                const JsonEncoder.withIndent('  ').convert(data),
                style: const TextStyle(fontFamily: 'monospace', fontSize: 13),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Message widget — shows a conversational message.
class _MessageWidget extends StatelessWidget {
  final AIAction action;
  final ColorScheme colorScheme;

  const _MessageWidget({
    required this.action,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Row(
          children: [
            Icon(Icons.info_outline, color: colorScheme.primary),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                action.text ?? action.message ?? '',
                style: Theme.of(context).textTheme.bodyLarge,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

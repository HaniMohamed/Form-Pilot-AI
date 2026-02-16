/// Debug panel — shows current answers, request log, action log, and session info.
///
/// Provides a real-time view of the conversation state for development
/// and testing purposes. Logs every request sent to the API and every
/// response received (newest first).
library;

import 'dart:convert';

import 'package:flutter/material.dart';

import '../models/ai_action.dart';

/// The debug panel showing current state in collapsible sections.
class DebugPanel extends StatelessWidget {
  final String? formFilename;
  final Map<String, dynamic> answers;
  final AIAction? currentAction;
  final List<AIAction> actionLog;
  final List<Map<String, dynamic>> requestLog;
  final String? conversationId;

  const DebugPanel({
    super.key,
    required this.formFilename,
    required this.answers,
    required this.currentAction,
    required this.actionLog,
    required this.requestLog,
    required this.conversationId,
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
              Icon(Icons.bug_report_outlined, size: 18, color: colorScheme.primary),
              const SizedBox(width: 8),
              Text(
                'Debug',
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: colorScheme.onSurface,
                ),
              ),
            ],
          ),
        ),

        // Content
        Expanded(
          child: formFilename == null
              ? _buildEmptyState(colorScheme)
              : ListView(
                  padding: const EdgeInsets.all(8),
                  children: [
                    _buildSessionInfo(colorScheme),
                    const SizedBox(height: 4),
                    _buildAnswersSection(colorScheme),
                    const SizedBox(height: 4),
                    _buildRequestLogSection(colorScheme),
                    const SizedBox(height: 4),
                    _buildActionLogSection(colorScheme),
                  ],
                ),
        ),
      ],
    );
  }

  Widget _buildEmptyState(ColorScheme colorScheme) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.code_outlined, size: 48, color: colorScheme.outline),
          const SizedBox(height: 12),
          Text(
            'Debug info will appear here',
            style: TextStyle(color: colorScheme.outline),
          ),
        ],
      ),
    );
  }

  Widget _buildSessionInfo(ColorScheme colorScheme) {
    return _DebugSection(
      title: 'Session',
      icon: Icons.key,
      initiallyExpanded: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _kvRow('Form', formFilename ?? '-'),
          _kvRow('Conversation ID', conversationId ?? '-'),
          _kvRow('Answers', '${answers.length}'),
          _kvRow('Requests', '${requestLog.length}'),
          _kvRow('Responses', '${actionLog.length}'),
        ],
      ),
    );
  }

  Widget _buildAnswersSection(ColorScheme colorScheme) {
    return _DebugSection(
      title: 'Answers (${answers.length})',
      icon: Icons.check_circle_outline,
      initiallyExpanded: true,
      child: answers.isEmpty
          ? const Padding(
              padding: EdgeInsets.all(8),
              child: Text(
                'No answers yet',
                style: TextStyle(
                  color: Colors.grey,
                  fontStyle: FontStyle.italic,
                ),
              ),
            )
          : _JsonView(data: answers),
    );
  }

  Widget _buildRequestLogSection(ColorScheme colorScheme) {
    return _DebugSection(
      title: 'Request Log (${requestLog.length})',
      icon: Icons.upload_outlined,
      initiallyExpanded: false,
      child: requestLog.isEmpty
          ? const Padding(
              padding: EdgeInsets.all(8),
              child: Text(
                'No requests yet',
                style: TextStyle(
                  color: Colors.grey,
                  fontStyle: FontStyle.italic,
                ),
              ),
            )
          : Column(
              children: [
                // Show requests in reverse order (newest first)
                for (int i = requestLog.length - 1; i >= 0; i--)
                  _RequestLogEntry(
                    index: i + 1,
                    data: requestLog[i],
                    isLatest: i == requestLog.length - 1,
                  ),
              ],
            ),
    );
  }

  Widget _buildActionLogSection(ColorScheme colorScheme) {
    return _DebugSection(
      title: 'Action Log (${actionLog.length})',
      icon: Icons.list_alt_outlined,
      initiallyExpanded: true,
      child: actionLog.isEmpty
          ? const Padding(
              padding: EdgeInsets.all(8),
              child: Text(
                'No actions yet',
                style: TextStyle(
                  color: Colors.grey,
                  fontStyle: FontStyle.italic,
                ),
              ),
            )
          : Column(
              children: [
                // Show actions in reverse order (newest first)
                for (int i = actionLog.length - 1; i >= 0; i--)
                  _ActionLogEntry(
                    index: i + 1,
                    action: actionLog[i],
                    isLatest: i == actionLog.length - 1,
                  ),
              ],
            ),
    );
  }

  Widget _kvRow(String key, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Text(
            '$key: ',
            style: const TextStyle(
              fontWeight: FontWeight.w600,
              fontSize: 12,
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                fontFamily: 'monospace',
                fontSize: 12,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

/// A single action entry in the log, with a header showing the index and
/// action type, and a collapsible JSON body.
class _ActionLogEntry extends StatelessWidget {
  final int index;
  final AIAction action;
  final bool isLatest;

  const _ActionLogEntry({
    required this.index,
    required this.action,
    required this.isLatest,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final actionType = action.raw['action'] as String? ?? 'UNKNOWN';

    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Container(
        decoration: BoxDecoration(
          color: isLatest
              ? colorScheme.primaryContainer.withValues(alpha: 0.3)
              : colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(6),
          border: isLatest
              ? Border.all(color: colorScheme.primary.withValues(alpha: 0.4))
              : null,
        ),
        child: ExpansionTile(
          dense: true,
          tilePadding: const EdgeInsets.symmetric(horizontal: 10),
          childrenPadding: const EdgeInsets.fromLTRB(10, 0, 10, 8),
          // Show the latest action expanded by default
          initiallyExpanded: isLatest,
          leading: Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: colorScheme.primary.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              '#$index',
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.bold,
                color: colorScheme.primary,
              ),
            ),
          ),
          title: Row(
            children: [
              _ActionTypeBadge(actionType: actionType),
              const SizedBox(width: 6),
              if (action.fieldId != null)
                Expanded(
                  child: Text(
                    action.fieldId!,
                    style: TextStyle(
                      fontSize: 11,
                      color: colorScheme.onSurfaceVariant,
                      fontFamily: 'monospace',
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
          ),
          children: [
            _JsonView(data: action.toJson()),
          ],
        ),
      ),
    );
  }
}

/// A single request entry in the log, with a header showing the index
/// and a summary, and a collapsible JSON body.
class _RequestLogEntry extends StatelessWidget {
  final int index;
  final Map<String, dynamic> data;
  final bool isLatest;

  const _RequestLogEntry({
    required this.index,
    required this.data,
    required this.isLatest,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final userMessage = data['user_message'] as String? ?? '';
    final hasToolResults = data.containsKey('tool_results');

    // Build a short summary for the tile header
    final String summary;
    if (hasToolResults) {
      summary = 'tool_results';
    } else if (userMessage.isEmpty) {
      summary = '(init)';
    } else if (userMessage.length > 40) {
      summary = '${userMessage.substring(0, 40)}...';
    } else {
      summary = userMessage;
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Container(
        decoration: BoxDecoration(
          color: isLatest
              ? Colors.orange.withValues(alpha: 0.08)
              : colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(6),
          border: isLatest
              ? Border.all(color: Colors.orange.withValues(alpha: 0.4))
              : null,
        ),
        child: ExpansionTile(
          dense: true,
          tilePadding: const EdgeInsets.symmetric(horizontal: 10),
          childrenPadding: const EdgeInsets.fromLTRB(10, 0, 10, 8),
          initiallyExpanded: isLatest,
          leading: Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: Colors.orange.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              '#$index',
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.bold,
                color: Colors.orange.shade800,
              ),
            ),
          ),
          title: Row(
            children: [
              Icon(
                hasToolResults ? Icons.build_outlined : Icons.send_outlined,
                size: 12,
                color: Colors.orange.shade700,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  summary,
                  style: TextStyle(
                    fontSize: 11,
                    color: colorScheme.onSurfaceVariant,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          children: [
            _JsonView(data: data),
          ],
        ),
      ),
    );
  }
}

/// A small colored badge showing the action type.
class _ActionTypeBadge extends StatelessWidget {
  final String actionType;

  const _ActionTypeBadge({required this.actionType});

  @override
  Widget build(BuildContext context) {
    final (color, icon) = _actionStyle(actionType);

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: color),
          const SizedBox(width: 3),
          Text(
            actionType,
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  /// Map action type to a color and icon for visual distinction.
  static (Color, IconData) _actionStyle(String type) {
    return switch (type) {
      'MESSAGE' => (Colors.blue, Icons.chat_bubble_outline),
      'ASK_TEXT' => (Colors.teal, Icons.text_fields),
      'ASK_DROPDOWN' => (Colors.deepPurple, Icons.arrow_drop_down_circle_outlined),
      'ASK_CHECKBOX' => (Colors.indigo, Icons.check_box_outlined),
      'ASK_DATE' => (Colors.orange, Icons.calendar_today),
      'ASK_DATETIME' => (Colors.orange, Icons.access_time),
      'ASK_LOCATION' => (Colors.green, Icons.location_on_outlined),
      'TOOL_CALL' => (Colors.amber.shade800, Icons.build_outlined),
      'FORM_COMPLETE' => (Colors.green.shade700, Icons.check_circle_outline),
      _ => (Colors.grey, Icons.help_outline),
    };
  }
}

/// A collapsible debug section.
class _DebugSection extends StatelessWidget {
  final String title;
  final IconData icon;
  final bool initiallyExpanded;
  final Widget child;

  const _DebugSection({
    required this.title,
    required this.icon,
    this.initiallyExpanded = false,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Card(
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: colorScheme.outlineVariant.withValues(alpha: 0.5)),
      ),
      child: ExpansionTile(
        leading: Icon(icon, size: 16, color: colorScheme.primary),
        title: Text(
          title,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
        ),
        initiallyExpanded: initiallyExpanded,
        dense: true,
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        children: [child],
      ),
    );
  }
}

/// Pretty-printed JSON viewer.
class _JsonView extends StatelessWidget {
  final Map<String, dynamic> data;

  const _JsonView({required this.data});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(6),
      ),
      child: SelectableText(
        const JsonEncoder.withIndent('  ').convert(data),
        style: const TextStyle(fontFamily: 'monospace', fontSize: 11),
      ),
    );
  }
}

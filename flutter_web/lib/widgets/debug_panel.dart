/// Debug panel — shows current answers, last action JSON, and session info.
///
/// Provides a real-time view of the conversation state for development
/// and testing purposes.
library;

import 'dart:convert';

import 'package:flutter/material.dart';

import '../models/ai_action.dart';

/// The debug panel showing current state in collapsible sections.
class DebugPanel extends StatelessWidget {
  final String? formFilename;
  final Map<String, dynamic> answers;
  final AIAction? currentAction;
  final String? conversationId;

  const DebugPanel({
    super.key,
    required this.formFilename,
    required this.answers,
    required this.currentAction,
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
                    _buildLastActionSection(colorScheme),
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

  Widget _buildLastActionSection(ColorScheme colorScheme) {
    return _DebugSection(
      title: 'Last Action',
      icon: Icons.play_arrow_outlined,
      initiallyExpanded: true,
      child: currentAction == null
          ? const Padding(
              padding: EdgeInsets.all(8),
              child: Text(
                'No action yet',
                style: TextStyle(
                  color: Colors.grey,
                  fontStyle: FontStyle.italic,
                ),
              ),
            )
          : _JsonView(data: currentAction!.toJson()),
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

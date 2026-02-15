/// Schema selector widget — dropdown to pick a markdown form context or paste custom markdown.
library;

import 'package:flutter/material.dart';

import '../services/chat_service.dart';

/// Callback type for when a markdown form context is selected.
/// Receives the filename and markdown content.
typedef OnMarkdownSelected = void Function(String filename, String content);

/// Schema selector as a popup menu button in the app bar.
class SchemaSelector extends StatefulWidget {
  final ChatService chatService;
  final OnMarkdownSelected onMarkdownSelected;
  final bool isBackendConnected;

  const SchemaSelector({
    super.key,
    required this.chatService,
    required this.onMarkdownSelected,
    required this.isBackendConnected,
  });

  @override
  State<SchemaSelector> createState() => _SchemaSelectorState();
}

class _SchemaSelectorState extends State<SchemaSelector> {
  List<Map<String, dynamic>>? _availableSchemas;
  bool _loading = false;

  Future<void> _loadSchemas() async {
    if (_loading) return;
    setState(() => _loading = true);
    try {
      final schemas = await widget.chatService.listSchemas();
      setState(() {
        _availableSchemas = schemas;
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to load schemas: $e')),
        );
      }
    }
  }

  Future<void> _selectSchema(String filename) async {
    try {
      final result = await widget.chatService.getSchemaContent(filename);
      widget.onMarkdownSelected(result.filename, result.content);
    } on ChatServiceException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error loading schema: ${e.message}')),
        );
      }
    }
  }

  void _showCustomMarkdownDialog() {
    final controller = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Paste Custom Markdown'),
        content: SizedBox(
          width: 600,
          height: 400,
          child: TextField(
            controller: controller,
            maxLines: null,
            expands: true,
            decoration: const InputDecoration(
              hintText: '# My Form\n\n## Step 1\n...',
              border: OutlineInputBorder(),
            ),
            style: const TextStyle(fontFamily: 'monospace', fontSize: 13),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final content = controller.text.trim();
              if (content.isEmpty) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Markdown content is empty')),
                );
                return;
              }
              Navigator.of(ctx).pop();
              widget.onMarkdownSelected('custom.md', content);
            },
            child: const Text('Load Markdown'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<String>(
      icon: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.folder_open),
          const SizedBox(width: 4),
          const Text('Forms'),
          if (_loading) ...[
            const SizedBox(width: 4),
            const SizedBox(
              width: 12,
              height: 12,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ],
        ],
      ),
      tooltip: 'Select Form Definition',
      enabled: widget.isBackendConnected,
      onOpened: _loadSchemas,
      onSelected: (value) {
        if (value == '__custom__') {
          _showCustomMarkdownDialog();
        } else {
          _selectSchema(value);
        }
      },
      itemBuilder: (context) {
        final items = <PopupMenuEntry<String>>[];

        // Example schemas from backend
        if (_availableSchemas != null) {
          for (final schema in _availableSchemas!) {
            items.add(PopupMenuItem(
              value: schema['filename'] as String,
              child: ListTile(
                leading: const Icon(Icons.description, size: 20),
                title: Text(schema['title'] as String? ?? schema['filename'] as String),
                subtitle: Text(schema['filename'] as String),
                dense: true,
                contentPadding: EdgeInsets.zero,
              ),
            ));
          }
        }

        if (items.isNotEmpty) {
          items.add(const PopupMenuDivider());
        }

        // Custom markdown option
        items.add(const PopupMenuItem(
          value: '__custom__',
          child: ListTile(
            leading: Icon(Icons.edit_note, size: 20),
            title: Text('Custom Markdown...'),
            dense: true,
            contentPadding: EdgeInsets.zero,
          ),
        ));

        return items;
      },
    );
  }
}

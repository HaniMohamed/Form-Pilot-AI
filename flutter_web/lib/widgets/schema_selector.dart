/// Schema selector widget — dropdown to pick an example schema or upload custom JSON.
library;

import 'dart:convert';

import 'package:flutter/material.dart';

import '../models/form_schema.dart';
import '../services/chat_service.dart';

/// Schema selector as a popup menu button in the app bar.
class SchemaSelector extends StatefulWidget {
  final ChatService chatService;
  final ValueChanged<FormSchema> onSchemaSelected;
  final bool isBackendConnected;

  const SchemaSelector({
    super.key,
    required this.chatService,
    required this.onSchemaSelected,
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
      final schema = await widget.chatService.getSchema(filename);
      widget.onSchemaSelected(schema);
    } on ChatServiceException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error loading schema: ${e.message}')),
        );
      }
    }
  }

  void _showCustomSchemaDialog() {
    final controller = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Paste Custom Schema JSON'),
        content: SizedBox(
          width: 600,
          height: 400,
          child: TextField(
            controller: controller,
            maxLines: null,
            expands: true,
            decoration: const InputDecoration(
              hintText: '{\n  "form_id": "...",\n  "fields": [...]\n}',
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
              try {
                final json = jsonDecode(controller.text) as Map<String, dynamic>;
                final schema = FormSchema.fromJson(json);
                Navigator.of(ctx).pop();
                widget.onSchemaSelected(schema);
              } catch (e) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('Invalid schema: $e')),
                );
              }
            },
            child: const Text('Load Schema'),
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
          const Text('Schema'),
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
      tooltip: 'Select Form Schema',
      enabled: widget.isBackendConnected,
      onOpened: _loadSchemas,
      onSelected: (value) {
        if (value == '__custom__') {
          _showCustomSchemaDialog();
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
                title: Text(schema['form_id'] as String? ?? schema['filename'] as String),
                subtitle: Text('${schema['field_count']} fields'),
                dense: true,
                contentPadding: EdgeInsets.zero,
              ),
            ));
          }
        }

        if (items.isNotEmpty) {
          items.add(const PopupMenuDivider());
        }

        // Custom schema option
        items.add(const PopupMenuItem(
          value: '__custom__',
          child: ListTile(
            leading: Icon(Icons.code, size: 20),
            title: Text('Custom JSON...'),
            dense: true,
            contentPadding: EdgeInsets.zero,
          ),
        ));

        return items;
      },
    );
  }
}

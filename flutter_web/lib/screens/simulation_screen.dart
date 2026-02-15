/// Main simulation screen with two-panel layout:
/// 1. Chat panel (left) — messages, inline action widgets, and text input
/// 2. JSON debug panel (right) — current answers, last action, field visibility
library;

import 'dart:convert';

import 'package:flutter/material.dart';

import '../models/ai_action.dart';
import '../models/form_schema.dart';
import '../services/chat_service.dart';
import '../widgets/chat_panel.dart';
import '../widgets/debug_panel.dart';
import '../widgets/schema_selector.dart';

/// Represents a single chat message in the conversation.
class ChatMessage {
  final String text;
  final bool isUser;
  final DateTime timestamp;

  /// If non-null, this message represents a FORM_COMPLETE result.
  /// The chat panel renders it as a rich card with the final data.
  final Map<String, dynamic>? formCompleteData;

  const ChatMessage({
    required this.text,
    required this.isUser,
    required this.timestamp,
    this.formCompleteData,
  });
}

/// The main simulation screen that drives the form-filling conversation.
class SimulationScreen extends StatefulWidget {
  const SimulationScreen({super.key});

  @override
  State<SimulationScreen> createState() => _SimulationScreenState();
}

class _SimulationScreenState extends State<SimulationScreen> {
  final ChatService _chatService = ChatService();

  // Session state
  FormSchema? _schema;
  String? _conversationId;
  AIAction? _currentAction;
  Map<String, dynamic> _answers = {};
  List<ChatMessage> _messages = [];
  bool _isLoading = false;
  bool _isBackendConnected = false;

  @override
  void initState() {
    super.initState();
    _checkBackendHealth();
  }

  @override
  void dispose() {
    _chatService.dispose();
    super.dispose();
  }

  /// Check if the backend is running.
  Future<void> _checkBackendHealth() async {
    try {
      await _chatService.healthCheck();
      setState(() => _isBackendConnected = true);
    } catch (_) {
      setState(() => _isBackendConnected = false);
    }
  }

  /// Load a schema and start a new conversation session.
  Future<void> _onSchemaSelected(FormSchema schema) async {
    setState(() {
      _schema = schema;
      _conversationId = null;
      _currentAction = null;
      _answers = {};
      _messages = [];
      _isLoading = true;
    });

    try {
      // Send empty message to initialize the session
      final response = await _chatService.sendMessage(
        schema: schema,
        userMessage: '',
      );

      setState(() {
        _conversationId = response.conversationId;
        _currentAction = response.action;
        _answers = response.answers;
        _isLoading = false;
      });

      // Add the AI greeting to the chat
      final greeting = response.action.message ?? response.action.label ?? '';
      if (greeting.isNotEmpty) {
        setState(() {
          _messages.add(ChatMessage(
            text: greeting,
            isUser: false,
            timestamp: DateTime.now(),
          ));
        });
      }
    } on ChatServiceException catch (e) {
      setState(() {
        _isLoading = false;
        _messages.add(ChatMessage(
          text: 'Error: ${e.message}',
          isUser: false,
          timestamp: DateTime.now(),
        ));
      });
    }
  }

  /// Process a user message through the chat service.
  Future<void> _onUserMessage(String message) async {
    if (_schema == null || message.trim().isEmpty) return;

    // Add user message to chat
    setState(() {
      _messages.add(ChatMessage(
        text: message,
        isUser: true,
        timestamp: DateTime.now(),
      ));
      _isLoading = true;
    });

    try {
      final response = await _chatService.sendMessage(
        schema: _schema!,
        userMessage: message,
        conversationId: _conversationId,
      );

      setState(() {
        _conversationId = response.conversationId;
        _currentAction = response.action;
        _answers = response.answers;
        _isLoading = false;
      });

      // For FORM_COMPLETE, add a rich card message with the final data
      if (response.action.isFormComplete) {
        final summaryText =
            response.action.message ?? response.action.text ?? '';
        setState(() {
          _messages.add(ChatMessage(
            text: summaryText,
            isUser: false,
            timestamp: DateTime.now(),
            formCompleteData: response.action.data,
          ));
        });
      } else {
        // Add AI response message to chat
        final aiMessage = response.action.message ??
            response.action.text ??
            response.action.label ??
            '';
        if (aiMessage.isNotEmpty) {
          setState(() {
            _messages.add(ChatMessage(
              text: aiMessage,
              isUser: false,
              timestamp: DateTime.now(),
            ));
          });
        }
      }
    } on ChatServiceException catch (e) {
      setState(() {
        _isLoading = false;
        _messages.add(ChatMessage(
          text: 'Error: ${e.message}',
          isUser: false,
          timestamp: DateTime.now(),
        ));
      });
    }
  }

  /// Reset the current conversation.
  Future<void> _onReset() async {
    if (_conversationId != null) {
      try {
        await _chatService.resetSession(_conversationId!);
      } catch (_) {
        // Ignore reset errors — just clear local state
      }
    }

    if (_schema != null) {
      await _onSchemaSelected(_schema!);
    }
  }

  /// Show the raw schema JSON in a dialog.
  void _showSchemaDialog() {
    if (_schema == null) return;
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Form Schema'),
        content: SizedBox(
          width: 600,
          child: SingleChildScrollView(
            child: SelectableText(
              const JsonEncoder.withIndent('  ').convert(_schema!.toJson()),
              style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Icon(Icons.smart_toy_outlined, size: 28),
            const SizedBox(width: 8),
            const Text('FormPilot AI'),
            const SizedBox(width: 16),
            // Backend connection indicator
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: _isBackendConnected
                    ? Colors.green.withValues(alpha: 0.15)
                    : Colors.red.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    _isBackendConnected ? Icons.cloud_done : Icons.cloud_off,
                    size: 14,
                    color: _isBackendConnected ? Colors.green : Colors.red,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    _isBackendConnected ? 'Backend connected' : 'Backend offline',
                    style: TextStyle(
                      fontSize: 12,
                      color: _isBackendConnected ? Colors.green : Colors.red,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          SchemaSelector(
            chatService: _chatService,
            onSchemaSelected: _onSchemaSelected,
            isBackendConnected: _isBackendConnected,
          ),
          if (_schema != null) ...[
            IconButton(
              icon: const Icon(Icons.description_outlined),
              tooltip: 'Show Schema',
              onPressed: _showSchemaDialog,
            ),
            IconButton(
              icon: const Icon(Icons.refresh),
              tooltip: 'Reset Conversation',
              onPressed: _onReset,
            ),
          ],
          IconButton(
            icon: const Icon(Icons.sync),
            tooltip: 'Check Backend',
            onPressed: _checkBackendHealth,
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: _schema == null ? _buildWelcome() : _buildTwoPanelLayout(),
    );
  }

  Widget _buildWelcome() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.smart_toy_outlined,
            size: 80,
            color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.4),
          ),
          const SizedBox(height: 24),
          Text(
            'FormPilot AI',
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'Conversational Form Filling System',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: Colors.grey,
                ),
          ),
          const SizedBox(height: 32),
          if (!_isBackendConnected) ...[
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.orange.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.orange.withValues(alpha: 0.3)),
              ),
              child: const Column(
                children: [
                  Icon(Icons.warning_amber, color: Colors.orange, size: 32),
                  SizedBox(height: 8),
                  Text(
                    'Backend is not running',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  SizedBox(height: 4),
                  Text(
                    'Start the backend with:\nuvicorn backend.api.app:app --reload',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontFamily: 'monospace', fontSize: 13),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
          ],
          const Text(
            'Select a form schema from the toolbar to begin',
            style: TextStyle(fontSize: 16, color: Colors.grey),
          ),
        ],
      ),
    );
  }

  Widget _buildTwoPanelLayout() {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Responsive: stack vertically on narrow screens
        if (constraints.maxWidth < 700) {
          return _buildStackedLayout();
        }
        return _buildSideBySideLayout();
      },
    );
  }

  Widget _buildSideBySideLayout() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Chat panel (left, takes most space)
        Expanded(
          flex: 3,
          child: ChatPanel(
            messages: _messages,
            isLoading: _isLoading,
            onSendMessage: _onUserMessage,
            isSessionActive: _conversationId != null,
            currentAction: _currentAction,
          ),
        ),
        const VerticalDivider(width: 1),
        // Debug panel (right)
        Expanded(
          flex: 2,
          child: DebugPanel(
            schema: _schema,
            answers: _answers,
            currentAction: _currentAction,
            conversationId: _conversationId,
          ),
        ),
      ],
    );
  }

  Widget _buildStackedLayout() {
    return DefaultTabController(
      length: 2,
      child: Column(
        children: [
          const TabBar(
            tabs: [
              Tab(icon: Icon(Icons.chat), text: 'Chat'),
              Tab(icon: Icon(Icons.bug_report), text: 'Debug'),
            ],
          ),
          Expanded(
            child: TabBarView(
              children: [
                ChatPanel(
                  messages: _messages,
                  isLoading: _isLoading,
                  onSendMessage: _onUserMessage,
                  isSessionActive: _conversationId != null,
                  currentAction: _currentAction,
                ),
                DebugPanel(
                  schema: _schema,
                  answers: _answers,
                  currentAction: _currentAction,
                  conversationId: _conversationId,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

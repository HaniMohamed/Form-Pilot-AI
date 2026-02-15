/// Main simulation screen with two-panel layout:
/// 1. Chat panel (left) — messages, inline action widgets, and text input
/// 2. JSON debug panel (right) — current answers, last action
library;

import 'package:flutter/material.dart';

import '../models/ai_action.dart';
import '../services/chat_service.dart';
import '../services/mock_tools.dart';
import '../widgets/chat_panel.dart';
import '../widgets/debug_panel.dart';
import '../widgets/schema_selector.dart';

/// Represents a single chat message in the conversation.
class ChatMessage {
  final String text;
  final bool isUser;
  final DateTime timestamp;

  /// If true, this message represents a tool call executing in the background.
  final bool isToolCall;

  /// If non-null, this message represents a FORM_COMPLETE result.
  /// The chat panel renders it as a rich card with the final data.
  final Map<String, dynamic>? formCompleteData;

  const ChatMessage({
    required this.text,
    required this.isUser,
    required this.timestamp,
    this.isToolCall = false,
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
  String? _formContextMd;
  String? _formFilename;
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

  /// Load a markdown form and start a new conversation session.
  Future<void> _onMarkdownSelected(String filename, String content) async {
    setState(() {
      _formContextMd = content;
      _formFilename = filename;
      _conversationId = null;
      _currentAction = null;
      _answers = {};
      _messages = [];
      _isLoading = true;
    });

    try {
      // Send empty message to initialize the session and get greeting
      final response = await _chatService.sendMessage(
        formContextMd: content,
        userMessage: '',
      );

      setState(() {
        _conversationId = response.conversationId;
        _currentAction = response.action;
        _answers = response.answers;
        _isLoading = false;
      });

      // Add the AI greeting to the chat
      final greeting = response.action.message ?? response.action.text ?? '';
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
    if (_formContextMd == null || message.trim().isEmpty) return;

    // Add user message to chat
    setState(() {
      _messages.add(ChatMessage(
        text: message,
        isUser: true,
        timestamp: DateTime.now(),
      ));
      _isLoading = true;
    });

    await _sendToBackend(userMessage: message);
  }

  /// Send a message (or tool results) to the backend and handle the response.
  ///
  /// Automatically handles TOOL_CALL responses by executing mock tools
  /// and sending results back.
  Future<void> _sendToBackend({
    String userMessage = '',
    List<Map<String, dynamic>>? toolResults,
  }) async {
    try {
      final response = await _chatService.sendMessage(
        formContextMd: _formContextMd!,
        userMessage: userMessage,
        conversationId: _conversationId,
        toolResults: toolResults,
      );

      setState(() {
        _conversationId = response.conversationId;
        _currentAction = response.action;
        _answers = response.answers;
        _isLoading = false;
      });

      // Handle TOOL_CALL: execute mock tool and send results back
      if (response.action.isToolCall) {
        await _handleToolCall(response.action);
        return;
      }

      // Handle FORM_COMPLETE: show rich card
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
        return;
      }

      // Handle regular actions: add AI message to chat
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

  /// Handle a TOOL_CALL action: show a status message, execute the mock tool,
  /// and send the result back to the backend.
  Future<void> _handleToolCall(AIAction action) async {
    final toolName = action.toolName ?? 'unknown';
    final toolArgs = action.toolArgs ?? {};
    final toolMessage = action.message ?? 'Executing $toolName...';

    // Show a temporary tool-executing message in chat
    final toolMsg = ChatMessage(
      text: toolMessage,
      isUser: false,
      timestamp: DateTime.now(),
      isToolCall: true,
    );
    setState(() {
      _messages.add(toolMsg);
      _isLoading = true;
    });

    // Small delay to simulate network/processing time
    await Future<void>.delayed(const Duration(milliseconds: 500));

    // Execute the mock tool
    final mockResult = executeMockTool(toolName, toolArgs);

    // Remove the temporary tool message — the next AI response will replace it
    setState(() {
      _messages.remove(toolMsg);
    });

    // Send the tool result back to the backend
    await _sendToBackend(
      toolResults: [
        {
          'tool_name': toolName,
          'tool_args': toolArgs,
          'result': mockResult,
        },
      ],
    );
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

    if (_formContextMd != null && _formFilename != null) {
      await _onMarkdownSelected(_formFilename!, _formContextMd!);
    }
  }

  /// Show the markdown content in a dialog.
  void _showMarkdownDialog() {
    if (_formContextMd == null) return;
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Form Definition: ${_formFilename ?? ""}'),
        content: SizedBox(
          width: 600,
          child: SingleChildScrollView(
            child: SelectableText(
              _formContextMd!,
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
            onMarkdownSelected: _onMarkdownSelected,
            isBackendConnected: _isBackendConnected,
          ),
          if (_formContextMd != null) ...[
            IconButton(
              icon: const Icon(Icons.description_outlined),
              tooltip: 'Show Form Definition',
              onPressed: _showMarkdownDialog,
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
      body: _formContextMd == null ? _buildWelcome() : _buildTwoPanelLayout(),
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
            'Select a form definition from the toolbar to begin',
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
            formFilename: _formFilename,
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
                  formFilename: _formFilename,
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

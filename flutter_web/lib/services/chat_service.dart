/// Service for communicating with the FormPilot AI backend.
///
/// Handles HTTP calls to /api/chat, /api/schemas,
/// and /api/sessions/reset endpoints.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/ai_action.dart';

/// Exception thrown when the backend returns an error.
class ChatServiceException implements Exception {
  final String message;
  final int? statusCode;

  const ChatServiceException(this.message, {this.statusCode});

  @override
  String toString() => 'ChatServiceException($statusCode): $message';
}

/// Service for communicating with the FormPilot AI Python backend.
class ChatService {
  final String baseUrl;
  final http.Client _client;

  ChatService({
    this.baseUrl = 'http://localhost:8000/api',
    http.Client? client,
  }) : _client = client ?? http.Client();

  /// Send a chat message and get the AI response.
  ///
  /// [formContextMd] is the markdown form context sent on every request.
  /// [userMessage] is the user's text input.
  /// [conversationId] is the session ID (null for first message).
  /// [toolResults] is the results from TOOL_CALL actions (null if none).
  Future<ChatResponse> sendMessage({
    required String formContextMd,
    required String userMessage,
    String? conversationId,
    List<Map<String, dynamic>>? toolResults,
  }) async {
    final body = {
      'form_context_md': formContextMd,
      'user_message': userMessage,
      'conversation_id': ?conversationId,
      'tool_results': ?toolResults,
    };

    final response = await _post('/chat', body);
    return ChatResponse.fromJson(response);
  }

  /// List available example schemas from the backend.
  Future<List<Map<String, dynamic>>> listSchemas() async {
    final response = await _get('/schemas');
    return (response['schemas'] as List<dynamic>)
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  /// Get a specific schema file content by filename.
  Future<({String filename, String content})> getSchemaContent(
    String filename,
  ) async {
    final response = await _get('/schemas/$filename');
    return (
      filename: response['filename'] as String,
      content: response['content'] as String,
    );
  }

  /// Reset/delete a conversation session.
  Future<bool> resetSession(String conversationId) async {
    final response = await _post('/sessions/reset', {
      'conversation_id': conversationId,
    });
    return response['success'] as bool;
  }

  /// Check backend health.
  Future<Map<String, dynamic>> healthCheck() async {
    return _get('/health');
  }

  // --- Internal HTTP helpers ---

  Future<Map<String, dynamic>> _post(
    String path,
    Map<String, dynamic> body,
  ) async {
    final uri = Uri.parse('$baseUrl$path');
    try {
      final response = await _client
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(const Duration(seconds: 60));

      return _handleResponse(response);
    } on http.ClientException catch (e) {
      throw ChatServiceException(
        'Network error: ${e.message}. Is the backend running at $baseUrl?',
      );
    } catch (e) {
      if (e is ChatServiceException) rethrow;
      throw ChatServiceException('Unexpected error: $e');
    }
  }

  Future<Map<String, dynamic>> _get(String path) async {
    final uri = Uri.parse('$baseUrl$path');
    try {
      final response = await _client
          .get(uri, headers: {'Accept': 'application/json'})
          .timeout(const Duration(seconds: 10));

      return _handleResponse(response);
    } on http.ClientException catch (e) {
      throw ChatServiceException(
        'Network error: ${e.message}. Is the backend running at $baseUrl?',
      );
    } catch (e) {
      if (e is ChatServiceException) rethrow;
      throw ChatServiceException('Unexpected error: $e');
    }
  }

  Map<String, dynamic> _handleResponse(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return jsonDecode(response.body) as Map<String, dynamic>;
    }

    // Try to extract error detail from the response
    String detail;
    try {
      final errorBody = jsonDecode(response.body) as Map<String, dynamic>;
      detail = errorBody['detail']?.toString() ?? response.body;
    } catch (_) {
      detail = response.body;
    }

    throw ChatServiceException(
      detail,
      statusCode: response.statusCode,
    );
  }

  /// Clean up the HTTP client.
  void dispose() {
    _client.close();
  }
}

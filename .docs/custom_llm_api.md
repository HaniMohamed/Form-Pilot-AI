# Custom LLM API - Technical Reference

## Overview

The application supports a **Custom API** provider (in addition to Ollama) that communicates with any OpenAI-compatible chat completions endpoint. The implementation lives in `models.py` via the `UnifiedLLM` class.

## Configuration

| Parameter       | Description                          | Default                                                      |
| --------------- | ------------------------------------ | ------------------------------------------------------------ |
| `api_endpoint`  | Full URL of the chat completions API | `https://llm-platform.gosi.ins/api/chat/completions`         |
| `api_key`       | Bearer token for authentication      | *(required)*                                                 |
| `model_name`    | Model identifier string              | *(required)*                                                 |

## HTTP Request

**Method:** `POST`  
**Timeout:** 120 seconds

### Headers

```json
{
  "Authorization": "Bearer <api_key>",
  "accept": "application/json",
  "Content-Type": "application/json"
}
```

### Request Body

```json
{
  "model": "<model_name>",
  "messages": [
    {
      "role": "user",
      "content": "<prompt_text>"
    }
  ]
}
```

## Expected Response

The API must return an **OpenAI-compatible** chat completions response:

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "The review of this merge request shows..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 120,
    "completion_tokens": 300,
    "total_tokens": 420
  }
}
```

**Extraction logic** — the app reads:

```python
result["choices"][0]["message"]["content"]
```
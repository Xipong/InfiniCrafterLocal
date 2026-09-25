"""Subscription-only Codex Responses adapter for InfiniCrafter's authored LLM stages.

No Platform API key, tool execution, paid fallback or chat-completions downgrade.
"""
from __future__ import annotations

from typing import Any

from infini_local.services import codex_auth

RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})


def _output_text(response: dict) -> str:
    chunks: list[str] = []
    output = response.get("output")
    if not isinstance(output, list):
        raise codex_auth.CodexError("Codex returned no completed text output")
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message" or item.get("role") != "assistant":
            continue
        # Progress commentary is not the authored stage result. Preserve legacy
        # unphased messages, but never splice commentary into the final JSON.
        if item.get("phase") == "commentary":
            continue
        if item.get("status") not in (None, "completed"):
            raise codex_auth.CodexError("Codex returned incomplete text output")
        parts = item.get("content")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal":
                raise codex_auth.CodexError("Codex refused the text request")
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    text = "".join(chunks)
    if not text.strip() or len(text) > 2 * 1024 * 1024:
        raise codex_auth.CodexError("Codex returned no usable bounded text output")
    return text


def _request_payload(packet: dict[str, Any]) -> dict[str, Any]:
    model = packet.get("model")
    if not isinstance(model, str) or not model.strip() or model in {"auto", "default"}:
        raise codex_auth.CodexError("Choose an available Codex text model before generating")
    instructions: list[str] = []
    inputs: list[dict[str, Any]] = []
    messages = packet.get("messages")
    if not isinstance(messages, list) or not messages:
        raise codex_auth.CodexError("Codex text requires an authored stage packet")
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"system", "developer", "user", "assistant"} or not isinstance(message.get("content"), str):
            raise codex_auth.CodexError("Codex text received an unsupported message shape")
        role, content = message["role"], message["content"]
        if role == "system":
            instructions.append(content)
        else:
            content_type = "output_text" if role == "assistant" else "input_text"
            inputs.append({"type": "message", "role": role, "content": [{"type": content_type, "text": content}]})
    if not inputs:
        raise codex_auth.CodexError("Codex text requires a user or developer message")
    request: dict[str, Any] = {
        "model": model, "instructions": "\n\n".join(instructions), "input": inputs,
        "tools": [], "tool_choice": "auto", "parallel_tool_calls": False,
        "store": False, "stream": True, "include": [],
    }
    if packet.get("max_tokens") is not None:
        # Subscription /responses rejects max_output_tokens with HTTP 400.
        # Do not advertise this as a cost cap: only byte/time bounds remain.
        budget = packet["max_tokens"]
        if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
            raise codex_auth.CodexError("Invalid Codex stage output budget")
    format_hint = packet.get("response_format")
    if isinstance(format_hint, dict):
        kind = format_hint.get("type")
        if kind == "json_object":
            request["text"] = {"format": {"type": "json_object"}}
        elif kind == "json_schema" and isinstance(format_hint.get("json_schema"), dict):
            shape = format_hint["json_schema"]
            request["text"] = {"format": {"type": "json_schema", "name": str(shape.get("name") or "infini_json"), "strict": bool(shape.get("strict")), "schema": shape.get("schema")}}
        else:
            raise codex_auth.CodexError("Codex text received an unsupported JSON format")
    reasoning = packet.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
        if not effort and reasoning and not packet.get("reasoning_effort"):
            raise codex_auth.CodexError("Codex text supports effort reasoning, not a separate token budget")
        if effort:
            if effort not in EFFORTS:
                raise codex_auth.CodexError("Codex text reasoning effort is not supported by the transport")
            request["reasoning"] = {"effort": effort}
    elif reasoning is not None:
        raise codex_auth.CodexError("Codex text reasoning must be an object")
    if "reasoning" not in request and packet.get("reasoning_effort"):
        effort = packet["reasoning_effort"]
        if effort not in EFFORTS:
            raise codex_auth.CodexError("Codex text reasoning effort is not supported by the transport")
        request["reasoning"] = {"effort": effort}
    # Codex reasoning models do not expose a compatible temperature knob.
    return request


def generate_chat(packet: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    request = _request_payload(packet)
    credentials = codex_auth.get_credentials()
    response = codex_auth.post_sse(RESPONSES_URL, request, headers={
        "Authorization": "Bearer " + credentials.access_token,
        "ChatGPT-Account-Id": credentials.account_id,
        "originator": "infinicrafter",
    }, timeout=timeout)
    content = _output_text(response)
    decoded_content = codex_auth._decode_unicode_runs(content)
    if any(secret and len(secret) >= 8 and secret in decoded_content
           for secret in (credentials.access_token, credentials.refresh_token, credentials.account_id)):
        raise codex_auth.CodexError("Codex response contained a session credential; output rejected")
    usage = response.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    safe_usage: dict[str, Any] = {
        key: usage[key] for key in ("input_tokens", "output_tokens", "total_tokens")
        if isinstance(usage.get(key), int) and not isinstance(usage[key], bool) and usage[key] >= 0
    }
    # Preserve counters used by usage diagnostics without forwarding arbitrary
    # provider metadata (which can include session credentials).
    for details_key, counter_key in (
        ("input_tokens_details", "cached_tokens"),
        ("output_tokens_details", "reasoning_tokens"),
    ):
        details = usage.get(details_key)
        counter = details.get(counter_key) if isinstance(details, dict) else None
        if isinstance(counter, int) and not isinstance(counter, bool) and counter >= 0:
            safe_usage[details_key] = {counter_key: counter}
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": safe_usage,
        "_debug": {"apiMode": "codex_subscription_sse", "requestMode": "exact", "provider": "openai_codex"},
    }

"""Offline regressions for the subscription adapter's Responses/Chat boundary."""

from copy import deepcopy
from io import BytesIO
import json

import pytest

from infini_local.services import codex_auth, codex_text_backend as backend


def _message(text, *, phase=None, **extra):
    message = {
        "type": "message", "role": "assistant", "status": "completed",
        "content": [{"type": "output_text", "text": text}], **extra,
    }
    if phase is not None:
        message["phase"] = phase
    return message


def _packet():
    return {"model": "test-codex-model", "messages": [{"role": "user", "content": "Return the authored JSON."}]}


@pytest.fixture
def subscription(monkeypatch):
    credentials = codex_auth.Credentials(
        "test-access-not-real", "test-refresh-not-real", "test-account-not-real", 9999999999,
    )
    monkeypatch.setattr(codex_auth, "get_credentials", lambda: credentials)
    response = {"status": "completed", "output": [_message('{"ok":true}')]}
    monkeypatch.setattr(codex_auth, "post_sse", lambda *args, **kwargs: deepcopy(response))
    return response, credentials


def test_commentary_is_not_concatenated_into_final_authored_json():
    response = {"output": [
        _message("I will validate the item first.\n", phase="commentary"),
        {"type": "reasoning", "summary": []},
        _message('{"item":"Клинок"}', phase="final_answer"),
    ]}
    original = deepcopy(response)
    text = backend._output_text(response)
    assert text == '{"item":"Клинок"}'
    assert json.loads(text) == {"item": "Клинок"}
    assert response == original


def test_commentary_only_completion_is_not_a_successful_stage_result():
    with pytest.raises(codex_auth.CodexError, match="text output"):
        backend._output_text({"output": [_message('{"status":"working"}', phase="commentary")]})


@pytest.mark.parametrize("status", ["in_progress", "incomplete"])
def test_unfinished_final_message_is_rejected(status):
    with pytest.raises(codex_auth.CodexError, match="incomplete"):
        backend._output_text({"output": [_message('{"partial":', phase="final_answer", status=status)]})


@pytest.mark.parametrize("phase", [None, "final_answer"])
def test_legacy_and_final_message_parts_preserve_authored_text(phase):
    message = _message("", phase=phase)
    message.pop("status")  # The existing legacy transport does not require this field.
    message["content"] = [
        {"type": "output_text", "text": '{"label":'},
        {"type": "output_text", "text": '"Клинок"}'},
    ]
    assert backend._output_text({"output": [message]}) == '{"label":"Клинок"}'


def test_final_refusal_is_not_hidden_by_preceding_text():
    message = _message('{"ok":true}', phase="final_answer")
    message["content"].append({"type": "refusal", "refusal": "test refusal"})
    with pytest.raises(codex_auth.CodexError, match="refused"):
        backend._output_text({"output": [message]})


def test_assistant_history_uses_output_text_without_rewriting_the_packet():
    packet = _packet()
    packet["messages"] = [
        {"role": "system", "content": "Literal system contract"},
        {"role": "developer", "content": "Literal developer contract"},
        {"role": "user", "content": "First request"},
        {"role": "assistant", "content": '{"old":"Клинок"}'},
        {"role": "user", "content": "Repair only the invalid field."},
    ]
    original = deepcopy(packet)
    payload = backend._request_payload(packet)
    assert payload["instructions"] == "Literal system contract"
    assert payload["input"] == [
        {"type": "message", "role": message["role"], "content": [{
            "type": "output_text" if message["role"] == "assistant" else "input_text",
            "text": message["content"],
        }]}
        for message in packet["messages"][1:]
    ]
    assert packet == original
    assert payload["stream"] is True and payload["store"] is False
    assert payload["tools"] == []


def test_safe_usage_preserves_cached_and_reasoning_counts(subscription):
    response, credentials = subscription
    response["usage"] = {
        "input_tokens": 120, "output_tokens": 30, "total_tokens": 150,
        "input_tokens_details": {"cached_tokens": 100, "metadata": credentials.access_token},
        "output_tokens_details": {"reasoning_tokens": 20, "metadata": credentials.refresh_token},
        "attribution": credentials.account_id,
    }
    result = backend.generate_chat(_packet(), timeout=3)
    assert result["usage"] == {
        "input_tokens": 120, "output_tokens": 30, "total_tokens": 150,
        "input_tokens_details": {"cached_tokens": 100},
        "output_tokens_details": {"reasoning_tokens": 20},
    }
    for secret in (credentials.access_token, credentials.refresh_token, credentials.account_id):
        assert secret not in repr(result)


@pytest.mark.parametrize("value", [0, 7])
def test_usage_detail_counters_preserve_nonnegative_integers(subscription, value):
    response, _ = subscription
    response["usage"] = {
        "input_tokens_details": {"cached_tokens": value},
        "output_tokens_details": {"reasoning_tokens": value},
    }
    assert backend.generate_chat(_packet(), timeout=3)["usage"] == response["usage"]


@pytest.mark.parametrize("value", [True, False, -1, 1.5, "20", None, {}, []])
def test_usage_detail_counters_reject_non_counters(subscription, value):
    response, _ = subscription
    response["usage"] = {
        "input_tokens_details": {"cached_tokens": value},
        "output_tokens_details": {"reasoning_tokens": value},
    }
    assert backend.generate_chat(_packet(), timeout=3)["usage"] == {}


@pytest.mark.parametrize("details", [None, [], "metadata", 5])
def test_malformed_usage_detail_containers_are_not_forwarded(subscription, details):
    response, _ = subscription
    response["usage"] = {"input_tokens": 2, "input_tokens_details": details, "output_tokens_details": details}
    assert backend.generate_chat(_packet(), timeout=3)["usage"] == {"input_tokens": 2}


def test_final_output_still_rejects_unicode_escaped_credentials(subscription):
    response, credentials = subscription
    leaked = '{"nested":"\\u0074est-access-not-real"}'
    response["output"] = [
        _message("Preparing an answer.", phase="commentary"),
        _message(leaked, phase="final_answer"),
    ]
    with pytest.raises(codex_auth.CodexError, match="credential") as caught:
        backend.generate_chat(_packet(), timeout=3)
    assert credentials.access_token not in str(caught.value)


@pytest.mark.parametrize("inline_output", [True, False])
def test_phase_filtering_through_real_sse_parser(monkeypatch, inline_output):
    credentials = codex_auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account-not-real", 9999999999)
    monkeypatch.setattr(codex_auth, "get_credentials", lambda: credentials)
    messages = [
        _message("First I will inspect the schema.\n", phase="commentary"),
        _message('{"ok":true}', phase="final_answer"),
    ]
    completion = {"status": "completed", "usage": {"input_tokens_details": {"cached_tokens": 42}}}
    if inline_output:
        completion["output"] = messages
    events = [{"type": "response.output_item.done", "item": item} for item in messages]
    events.append({"type": "response.completed", "response": completion})
    stream = b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events)
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            return BytesIO(stream)

    monkeypatch.setattr(codex_auth.urlrequest, "build_opener", lambda *args: Opener())
    result = backend.generate_chat(_packet(), timeout=3)
    assert result["choices"][0]["message"]["content"] == '{"ok":true}'
    assert result["usage"] == {"input_tokens_details": {"cached_tokens": 42}}
    assert len(calls) == 1
    assert calls[0][0].full_url == backend.RESPONSES_URL

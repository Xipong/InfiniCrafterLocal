import hashlib
import json
from urllib.error import HTTPError

import pytest

from infini_local.core.llm_negotiation_notice import safe_notices
from infini_local.pipelines.transport import client, negotiation, profiles

PAYLOAD = {"messages": [], "response_format": {"type": "json_schema", "json_schema": {"name": "one"}}}
VALID = {"choices": [{"message": {"content": '{"name":"item"}'}}]}
INVALID = {"choices": [{"message": {"content": 'not json'}}]}


@pytest.fixture
def scope(monkeypatch, tmp_path):
    config = tmp_path / "config.env"
    raw = b'# infini-config-format: json-string-v1\nINFINI_OPENAI_COMPAT_API_KEY="fixture-key"\n'
    config.write_bytes(raw)
    monkeypatch.delenv("INFINI_SKIP_CONFIG_FILE", raising=False)
    monkeypatch.setattr(negotiation.bootstrap, "CONFIG_PATH", config)
    monkeypatch.setattr(negotiation.bootstrap, "CONFIG_LOADED_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(negotiation.bootstrap, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(negotiation, "_notices", {})
    monkeypatch.setattr(client, "_RESPONSES_CAPABILITY", {})
    monkeypatch.setattr(client, "_STRICT_SCHEMA_CAPABILITY", {})
    monkeypatch.setattr(profiles, "ensure_llm_auth_configured", lambda c: None)
    monkeypatch.setattr(client.diagnostics, "_dispatch_available", lambda: True)
    monkeypatch.setattr(client, "log_event", lambda *args: None)
    context = {"provider": "openai_compat", "profile_id": "llm_1", "model": "known-model",
               "api_mode": "responses", "base_url": "https://example.invalid/fixture", "api_key": "fixture-key"}
    return config, raw, context


def schema_error(body):
    error = HTTPError("https://example.invalid/fixture", 400, "rejected", None, None)
    error._infini_body = json.dumps({"error": {"message": body}})
    return error


@pytest.mark.parametrize("failure", ["invalid", "exception", "config_race", "frozen", "none"])
def test_responses_fallback_recovery_and_exact_restart_scope(scope, monkeypatch, failure):
    config, raw, context = scope
    attempts = []
    def responses(*args):
        attempts.append("responses")
        raise HTTPError("https://example.invalid/fixture", 404, "rejected", None, None)
    def chat(*args):
        attempts.append("chat")
        assert negotiation.snapshot()[-1]["state"] == "rejected"
        if failure == "config_race":
            config.write_bytes(raw + b"# concurrent Studio edit\n")
        if failure == "exception":
            raise RuntimeError("alternative failed")
        return dict(INVALID if failure == "invalid" else VALID)
    monkeypatch.setattr(client, "_llm_responses_json_single_context", responses)
    monkeypatch.setattr(client, "_llm_chat_json_single_context", chat)
    if failure == "frozen":
        monkeypatch.setenv("INFINI_SKIP_CONFIG_FILE", "1")
    if failure == "exception":
        with pytest.raises(RuntimeError):
            client._llm_json_single_context(PAYLOAD, 1, context)
    else:
        client._llm_json_single_context(PAYLOAD, 1, context)
    assert attempts == ["responses", "chat"]
    expected = ("recovery_failed" if failure in {"invalid","exception"} else
                "recovered_not_saved" if failure != "none" else "saved")
    assert negotiation.snapshot()[-1]["state"] == expected
    files = list(negotiation.bootstrap.CACHE_DIR.glob("llm-negotiation-v1/*.json"))
    assert len(files) == int(failure == "none")
    assert config.read_bytes() == raw + (b"# concurrent Studio edit\n" if failure == "config_race" else b"")
    if failure != "none":
        return
    assert json.loads(files[0].read_text()) == {"version": 1, "kind": "responses_to_chat"}
    assert not any(s in files[0].read_text() for s in ("fixture-key","example.invalid","known-model"))
    def next_chat(*args):
        attempts.append("chat")
        return dict(VALID)
    monkeypatch.setattr(client, "_llm_chat_json_single_context", next_chat)
    client._RESPONSES_CAPABILITY.clear()
    attempts.clear()
    client._llm_json_single_context(PAYLOAD,1,context)
    assert attempts == ["chat"]
    assert negotiation.snapshot()[-1]["state"] == "saved"
    negotiation._notices.clear()  # fresh Studio/backend process
    client._RESPONSES_CAPABILITY.clear()
    attempts.clear()
    client._llm_json_single_context(PAYLOAD,1,context)
    assert attempts == ["chat"]
    assert negotiation.snapshot()[-1]["state"] == "saved_reused"
    for changed in (context | {"profile_id":"llm_2"}, context | {"model":"other"}, context | {"api_key":"rotated"}):
        attempts.clear()
        client._llm_json_single_context(PAYLOAD,1,changed)
        assert attempts == ["responses","chat"]
    client._RESPONSES_CAPABILITY.clear()
    attempts.clear()
    monkeypatch.setenv("INFINI_SKIP_CONFIG_FILE","yes")
    client._llm_json_single_context(PAYLOAD,1,context)
    assert attempts == ["responses","chat"]


@pytest.mark.parametrize("profile_scope", [False, True])
def test_strict_schema_receipt_preserves_rejection_scope(scope, monkeypatch, profile_scope):
    _, _, context = scope
    attempts=[]
    def chat(payload, _timeout, _context, *, schema_downgraded):
        fmt=payload["response_format"]["type"]
        attempts.append(fmt)
        if fmt == "json_schema":
            raise schema_error("json_schema unsupported" if profile_scope else "json_schema too complex")
        assert schema_downgraded
        return dict(VALID)
    monkeypatch.setattr(client, "_llm_chat_json_exact_context", chat)
    client._llm_chat_json_single_context(PAYLOAD,1,context)
    assert attempts == ["json_schema","json_object"]
    assert negotiation.snapshot()[-1]["scope"] == ("profile" if profile_scope else "schema")
    assert negotiation.snapshot()[-1]["state"] == "saved"
    client._STRICT_SCHEMA_CAPABILITY.clear()
    attempts.clear()
    client._llm_chat_json_single_context(PAYLOAD,1,context)
    assert attempts == ["json_object"]
    client._STRICT_SCHEMA_CAPABILITY.clear()
    attempts.clear()
    another = PAYLOAD | {"response_format":{"type":"json_schema","json_schema":{"name":"another"}}}
    client._llm_chat_json_single_context(another,1,context)
    assert attempts == (["json_object"] if profile_scope else ["json_schema","json_object"])
    assert list(negotiation.bootstrap.CACHE_DIR.glob("llm-negotiation-v1/*.json"))


def test_studio_readout_whitelist_drops_unknowns_and_sensitive_fields():
    row={"kind":"schema_to_object","profile":"llm_2","scope":"schema","state":"saved"}
    assert safe_notices([row | {"error":"token-secret","baseUrl":"hidden"},
                         row | {"profile":"secret"},row | {"state":"untrusted"}]) == [row]


def test_disk_edit_refuses_old_in_memory_and_on_disk_scope(scope, monkeypatch):
    config, raw, context = scope
    attempts = []
    def responses(*args):
        attempts.append("responses")
        raise HTTPError("https://example.invalid/fixture", 404, "rejected", None, None)
    def chat(*args):
        attempts.append("chat")
        return dict(VALID)
    monkeypatch.setattr(client, "_llm_responses_json_single_context", responses)
    monkeypatch.setattr(client, "_llm_chat_json_single_context", chat)
    client._llm_json_single_context(PAYLOAD,1,context)
    attempts.clear()
    assert negotiation.snapshot()[-1]["state"] == "saved"
    old = list(negotiation.bootstrap.CACHE_DIR.glob("llm-negotiation-v1/*.json"))
    assert len(old) == 1 and client._RESPONSES_CAPABILITY
    config.write_bytes(raw+b"# edit after acknowledgement\n")
    assert negotiation.snapshot()[-1]["state"] == "saved_inactive"
    client._llm_json_single_context(PAYLOAD,1,context)
    assert attempts == ["responses","chat"]
    assert list(negotiation.bootstrap.CACHE_DIR.glob("llm-negotiation-v1/*.json")) == old
    assert negotiation.snapshot()[-1]["state"] == "recovered_not_saved"


@pytest.mark.parametrize("auto,ambiguous", [("auto", False), ("local-model", False), ("local_model", False), (None, True)])
def test_request_shape_recovery_and_unresolved_models_are_attempt_only(scope, monkeypatch, auto, ambiguous):
    _, _, context = scope
    if auto:
        context["model"] = auto
        monkeypatch.setattr(client, "resolve_llm_model", lambda ctx: "discovered-model")
    attempts = []
    def responses(*args):
        attempts.append("responses")
        if ambiguous:
            raise schema_error("unsupported parameter")
        raise HTTPError("https://example.invalid/fixture", 404, "rejected", None, None)
    def chat(*args):
        attempts.append("chat")
        return dict(VALID)
    monkeypatch.setattr(client, "_llm_responses_json_single_context", responses)
    monkeypatch.setattr(client, "_llm_chat_json_single_context", chat)
    for _ in range(2):
        client._llm_json_single_context(PAYLOAD,1,context)
        assert negotiation.snapshot()[-1]["scope"] == "attempt"
        assert negotiation.snapshot()[-1]["state"] == "recovered_not_saved"
    assert attempts == ["responses","chat"] * 2
    assert not list(negotiation.bootstrap.CACHE_DIR.glob("llm-negotiation-v1/*.json"))


@pytest.mark.parametrize("finish_reason, message_extra", [
    ("length",{}),("content_filter",{}),("tool_calls",{}),(None,{"refusal":"blocked"}),
    ("stop",{"tool_calls":[{"id":"a"}]}),
])
def test_json_after_refusal_or_nonfinal_completion_cannot_save(scope, monkeypatch, finish_reason, message_extra):
    _, _, context = scope
    def responses(*args):
        raise HTTPError("https://example.invalid/fixture", 404, "rejected", None, None)
    monkeypatch.setattr(client, "_llm_responses_json_single_context", responses)
    result = {"choices":[{"finish_reason":finish_reason,"message":{"content":'{}',**message_extra}}]}
    monkeypatch.setattr(client, "_llm_chat_json_single_context", lambda *a: result)
    client._llm_json_single_context(PAYLOAD,1,context)
    assert negotiation.snapshot()[-1]["state"] == "recovery_failed"
    assert not list(negotiation.bootstrap.CACHE_DIR.glob("llm-negotiation-v1/*.json"))
    assert not client._RESPONSES_CAPABILITY

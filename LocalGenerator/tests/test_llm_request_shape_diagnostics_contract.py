"""Contract: a provider request-shape rejection is explained and repaired for the run.

Google Gemini and some other OpenAI-compatible gateways reject the large strict
Gameplay Author JSON Schema with a bare ``400 INVALID_ARGUMENT`` before the model
ever reads the prompt.  That status alone is unactionable, so the transport must

* explain which configured format produced the rejected wire and which
  configuration is known to be accepted, and
* recover the stage in place — exactly like the Responses -> Chat Completions
  downgrade — by retrying the same prompt with ``json_object`` and logging that
  it did so, for this run only, without editing the user's config.env.

The response envelope is the only thing allowed to change: the authored prompt
already carries ``requiredJsonShape``, and correctness is owned by the local
validator and compiler, not by provider-side constrained decoding.
"""

import json
import email.message
import urllib.error as urlerror
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LLM_TRANSPORT = ROOT / "infini_local" / "pipelines" / "llm_transport.py"
LLM_PIPELINE = ROOT / "infini_local" / "pipelines" / "llm_authoring_pipeline.py"
SETTINGS_SCHEMA = ROOT / "infini_local" / "desktop" / "settings_schema.py"


def _http_error(code: int, body: str = "") -> urlerror.HTTPError:
    headers = email.message.Message()
    error = urlerror.HTTPError(
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        code,
        "Bad Request",
        headers,
        BytesIO(body.encode("utf-8")),
    )
    if body:
        setattr(error, "_infini_body", body)
    return error


def _schema_payload(schema_chars: int = 4000) -> dict:
    filler = {f"p{index}": {"type": "string"} for index in range(schema_chars // 40)}
    return {
        "model": "gemini-3.5-flash-lite",
        "messages": [{"role": "user", "content": "x"}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "infini_low_level_runtime_author",
                "strict": True,
                "schema": {"type": "object", "properties": filler},
            },
        },
    }


def _gemini_context() -> dict:
    return {
        "provider": "openai_compat",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.5-flash-lite",
        "api_mode": "responses",
        "profile_id": "llm_1",
        "label": "llm_1",
    }


def _check_schema_rejection_is_diagnosed_with_both_configurations():
    from infini_local.pipelines import llm_transport

    diagnosis = llm_transport.request_shape_rejection_diagnosis(
        _http_error(400, '{"error": {"code": 400, "status": "INVALID_ARGUMENT"}}'),
        _schema_payload(),
        _gemini_context(),
    )
    assert isinstance(diagnosis, dict)
    assert diagnosis["code"] == "provider_rejected_request_shape"
    assert diagnosis["status"] == 400
    assert diagnosis["sentResponseFormat"] == "json_schema"
    # The user must be told what is known to work, and it must not be applied silently.
    assert diagnosis["knownWorkingResponseFormat"] == "json_object"
    assert diagnosis["knownWorkingApiMode"] == "chat_completions"
    assert diagnosis["schemaChars"] > 0
    assert "INVALID_ARGUMENT" in diagnosis["providerBody"]
    hint = diagnosis["hint"]
    assert "json_object" in hint and "chat_completions" in hint
    assert "INFINI_LLM_RESPONSE_FORMAT" in hint and "INFINI_LLM_API_MODE" in hint
    # It must state that the prompt was never evaluated, so the user does not hunt the wrong bug.
    assert "не получила задание" in hint


def _check_unrelated_failures_are_not_misdiagnosed():
    from infini_local.pipelines import llm_transport

    # Not a schema request: nothing to explain about schema complexity.
    assert llm_transport.request_shape_rejection_diagnosis(
        _http_error(400),
        {"model": "m", "response_format": {"type": "json_object"}},
        _gemini_context(),
    ) is None
    # Auth/quota/server failures belong to their own owners.
    for code in (401, 403, 404, 429, 500, 503):
        assert llm_transport.request_shape_rejection_diagnosis(
            _http_error(code), _schema_payload(), _gemini_context()
        ) is None
    # Transport errors are not request-shape rejections.
    assert llm_transport.request_shape_rejection_diagnosis(
        TimeoutError("timed out"), _schema_payload(), _gemini_context()
    ) is None


def _check_diagnosis_never_mutates_or_replaces_the_authored_request():
    from infini_local.pipelines import llm_transport

    payload = _schema_payload()
    before = json.dumps(payload, sort_keys=True)
    llm_transport.request_shape_rejection_diagnosis(_http_error(400), payload, _gemini_context())
    assert json.dumps(payload, sort_keys=True) == before, "diagnosis must not touch the payload"
    # Diagnosis stays pure reporting: the recovery is performed by the transport
    # path that owns the retry, not smuggled through the diagnosis dict.
    diagnosis = llm_transport.request_shape_rejection_diagnosis(
        _http_error(400), payload, _gemini_context()
    )
    assert isinstance(diagnosis, dict)
    assert "response_format" not in diagnosis
    assert isinstance(diagnosis["knownWorkingResponseFormat"], str)


def _check_strict_schema_rejection_is_detected_only_for_schema_requests():
    from infini_local.pipelines import llm_transport

    schema_payload = _schema_payload()
    assert llm_transport._strict_schema_rejected(_http_error(400), schema_payload) is True
    # A 400 on an already-relaxed request is a real failure, not a downgrade trigger.
    assert llm_transport._strict_schema_rejected(
        _http_error(400), {"response_format": {"type": "json_object"}}
    ) is False
    assert llm_transport._strict_schema_rejected(_http_error(400), {}) is False
    # Other statuses and transport errors belong to their own owners.
    for code in (401, 403, 404, 429, 500, 503):
        assert llm_transport._strict_schema_rejected(_http_error(code), schema_payload) is False
    assert llm_transport._strict_schema_rejected(TimeoutError("timed out"), schema_payload) is False


def _check_downgrade_changes_only_the_response_envelope():
    from infini_local.pipelines import llm_transport

    payload = _schema_payload()
    original = json.dumps(payload, sort_keys=True)
    relaxed = llm_transport._payload_without_strict_schema(payload)
    # The authored request is never edited in place.
    assert json.dumps(payload, sort_keys=True) == original
    assert relaxed["response_format"] == {"type": "json_object"}
    # Everything that carries the authored task must survive byte-identically.
    for key in ("model", "messages"):
        assert relaxed[key] == payload[key]
    assert set(relaxed) == set(payload)


def _check_transport_retries_the_same_stage_with_json_object_and_logs_it(monkeypatch):
    from infini_local.pipelines import llm_transport

    llm_transport._reset_llm_pool_runtime_for_tests()
    context = _gemini_context()
    sent: list[dict] = []
    events: list[tuple[str, str, dict]] = []

    def fake_http_json(url, payload, timeout=0, headers=None):
        sent.append(payload)
        response_format = payload.get("response_format") or {}
        if response_format.get("type") == "json_schema":
            raise _http_error(400, '{"error": {"code": 400, "status": "INVALID_ARGUMENT"}}')
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    monkeypatch.setattr(llm_transport, "http_json", fake_http_json)
    monkeypatch.setattr(llm_transport, "ensure_llm_auth_configured", lambda ctx: None)
    monkeypatch.setattr(llm_transport, "log_event", lambda level, message, data=None: events.append((level, message, data or {})))

    result = llm_transport._llm_chat_json_single_context(_schema_payload(), 60, context)

    # The stage completed instead of failing the craft.
    assert result["choices"][0]["message"]["content"] == '{"ok": true}'
    # It was the same prompt, retried with a relaxed envelope.
    assert len(sent) == 2
    assert sent[0]["response_format"]["type"] == "json_schema"
    assert sent[1]["response_format"] == {"type": "json_object"}
    assert sent[1]["messages"] == sent[0]["messages"]
    # The repair is visible in the log, and says it is per-run only.
    downgrade = [data for level, message, data in events if "json_object" in message]
    assert downgrade, [message for _, message, _ in events]
    assert downgrade[0]["was"] == "json_schema"
    assert downgrade[0]["now"] == "json_object"
    assert "config.env" in downgrade[0]["repairedFor"]
    assert "INFINI_LLM_RESPONSE_FORMAT=json_object" in downgrade[0]["detail"]
    # The result is attributed as a transport retry so acceptance runs can count it.
    assert result["_debug"]["strictSchemaDowngraded"] is True
    assert result["_debug"]["responseFormatType"] == "json_object"

    # Once learned, the same profile must not pay for the rejected shape again.
    sent.clear()
    again = llm_transport._llm_chat_json_single_context(_schema_payload(), 60, context)
    assert again["_debug"]["strictSchemaDowngraded"] is True
    assert len(sent) == 1
    assert sent[0]["response_format"] == {"type": "json_object"}
    llm_transport._reset_llm_pool_runtime_for_tests()


def _check_downgrade_does_not_mask_unrelated_failures(monkeypatch):
    from infini_local.pipelines import llm_transport

    llm_transport._reset_llm_pool_runtime_for_tests()
    calls: list[dict] = []

    def always_400(url, payload, timeout=0, headers=None):
        calls.append(payload)
        raise _http_error(400, '{"error": {"code": 400}}')

    monkeypatch.setattr(llm_transport, "http_json", always_400)
    monkeypatch.setattr(llm_transport, "ensure_llm_auth_configured", lambda ctx: None)
    monkeypatch.setattr(llm_transport, "log_event", lambda *a, **k: None)

    # A provider that rejects json_object too must surface the failure, not loop.
    try:
        llm_transport._llm_chat_json_single_context(_schema_payload(), 60, _gemini_context())
    except urlerror.HTTPError as error:
        assert error.code == 400
    else:  # pragma: no cover - the contract requires the error to propagate
        raise AssertionError("a persistent 400 must reach the caller")
    assert len(calls) == 2, "exactly one relaxed retry, then give up"

    # A 429 is never treated as a shape problem: no retry at all.
    llm_transport._reset_llm_pool_runtime_for_tests()
    calls.clear()

    def always_429(url, payload, timeout=0, headers=None):
        calls.append(payload)
        raise _http_error(429, "rate limited")

    monkeypatch.setattr(llm_transport, "http_json", always_429)
    try:
        llm_transport._llm_chat_json_single_context(_schema_payload(), 60, _gemini_context())
    except urlerror.HTTPError as error:
        assert error.code == 429
    else:  # pragma: no cover
        raise AssertionError("rate limiting must reach the caller")
    assert len(calls) == 1
    llm_transport._reset_llm_pool_runtime_for_tests()


def _check_transport_and_author_surface_the_diagnosis():
    transport_text = LLM_TRANSPORT.read_text(encoding="utf-8")
    pipeline_text = LLM_PIPELINE.read_text(encoding="utf-8")
    # The chat path must attach and log the diagnosis on the failing request.
    assert "request_shape_rejection_diagnosis(error, candidate, context)" in transport_text
    assert '"LLM provider rejected the configured request shape"' in transport_text
    assert '_infini_shape_diagnosis' in transport_text
    # The Author must escalate it into the user-visible craft failure.
    assert '_infini_shape_diagnosis' in pipeline_text
    assert '"requestShapeRejection": diagnosis' in pipeline_text
    assert "request_shape_rejection_diagnosis" in transport_text.split("__all__")[-1]


def _check_api_presets_pin_the_working_transport_and_schema_stays_optional():
    from infini_local.desktop import settings_schema

    for name, preset in settings_schema.PRESETS.items():
        provider = preset.get("INFINI_LLM_PROVIDER")
        if provider not in {"openai_compat", "openrouter"}:
            continue
        assert preset.get("INFINI_LLM_RESPONSE_FORMAT") == "json_object", name
        assert preset.get("INFINI_LLM_API_MODE") == "chat_completions", name
    # json_schema must remain a selectable option, only documented as unsupported there.
    choices = settings_schema.OPTION_HELP["INFINI_LLM_RESPONSE_FORMAT"]
    assert set(choices) == {"auto", "json_schema", "json_object", "off"}
    assert "Gemini" in choices["json_schema"]
    assert "json_schema" in settings_schema.FIELD_HELP["INFINI_LLM_RESPONSE_FORMAT"]
    schema_text = SETTINGS_SCHEMA.read_text(encoding="utf-8")
    assert "INVALID_ARGUMENT" in schema_text


# One collected item per contract module: the checks above keep source order and
# their own tracebacks. The shared runner discovers them by prefix, so a new check
# cannot be silently left out of a hand-maintained dispatch list.
def test_llm_request_shape_diagnostics_contract_coarse_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request, prefix="_check_")

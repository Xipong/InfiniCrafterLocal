"""Native Codex account ownership, auth, subscription text/SSE/catalog/image contracts."""
from __future__ import annotations

import base64
from infini_local.core.runtime_authoring.capability_registry import visible_capabilities
import copy
from dataclasses import dataclass, field
import hashlib
import io
import json
import os
import stat
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from infini_local.pipelines import llm_transport as llm, pipeline_visual_config as config
from infini_local.services import codex_auth as auth, codex_catalog as catalog, codex_text_backend as backend
from test_provider_transport_contract import PIN, packet, wire

CODEX = "https://chatgpt.com/backend-api/codex"


def _assert_structured_outputs_subset(schema):
    """Offline wire gate, independent of the projector (not remote acceptance)."""
    unsupported = {"oneOf", "allOf", "not", "dependentRequired", "dependentSchemas", "if", "then", "else"}
    types = {str: "string", int: "integer", bool: "boolean", float: "number", type(None): "null", list: "array", dict: "object"}

    def visit(node, path=()):
        assert not (unsupported & node.keys()), f"unsupported provider keyword at {path}: {unsupported & node.keys()}"
        if "const" in node:
            assert node.get("type") == types[type(node["const"])], f"untyped provider const at {path}"
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False, path
            assert set(node.get("required", [])) == set(node.get("properties", {})), path
        for key in ("properties", "$defs"):
            for name, child in node.get(key, {}).items():
                visit(child, path + (key, name))
        if isinstance(node.get("items"), dict):
            visit(node["items"], path + ("items",))
        for index, child in enumerate(node.get("anyOf", [])):
            visit(child, path + ("anyOf", index))

    visit(schema)


@pytest.mark.parametrize("stage", ["author", "repair"])
def test_subscription_author_schema_types_every_const_without_changing_literal_contract(monkeypatch, stage):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines import author_item_contract as contract, llm_authoring_pipeline as author

    monkeypatch.setattr(llm, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    if stage == "author":
        local = contract.author_item_response_schema()
        request, _, _ = author.build_initial_author_request(
            {"name": "Workbench"}, {"name": "Sword"}, {}, {}, "schema-replay", model_name="gpt-6-sol",
        )
    else:
        local = contract.author_item_repair_response_schema()
        request = {
            "model": "gpt-6-sol", "messages": [{"role": "user", "content": "Repair the exact invalid leaf."}],
            "response_format": llm.llm_json_response_format(
                "infini_low_level_runtime_author_repair", schema=contract.author_item_provider_repair_response_schema, strict=True,
            ),
        }
    before = copy.deepcopy(request)
    wire = json.loads(json.dumps(backend._request_payload(request)))
    provider = wire["text"]["format"]["schema"]
    _assert_structured_outputs_subset(provider)
    types = {str: "string", int: "integer", bool: "boolean"}
    seen = []

    def compare(source, sent, path=()):
        if isinstance(source, dict):
            if "if" in source:
                # Exact finite-event partition, before required+nullable encoding.
                # The periodic case promotes periodTicks; other cases retain its
                # optional wrapper. No function-name/weapon routing is involved.
                selector = next(iter(source["if"]["properties"]))
                expected = source["if"]["properties"][selector]["const"]
                events = source["properties"][selector]["enum"]
                assert set(sent) == {"anyOf"}
                assert len(sent["anyOf"]) == len(events)
                for event, remote in zip(events, sent["anyOf"]):
                    case = copy.deepcopy({key: value for key, value in source.items() if key not in {"if", "then"}})
                    case["properties"][selector]["enum"] = [event]
                    if event == expected:
                        case["required"] += [key for key in source["then"]["required"] if key not in case["required"]]
                    compare(case, remote, path + ("event-case", event))
                return
            expected_keys = set(source)
            if "oneOf" in source:
                expected_keys = (expected_keys - {"oneOf"}) | {"anyOf"}
            if "properties" in source:
                expected_keys.add("required")
                assert set(sent["properties"]) == set(source["properties"]), path
            if "const" in source:
                expected_keys.add("type")
            assert set(sent) == expected_keys, path
            if "const" in source:
                expected = types[type(source["const"])]
                assert sent.get("type") == expected, f"untyped provider const at {path}: {sent}"
                assert sent == {**source, "type": expected}
                candidates = [source["const"], "other", "", 0, 1, 2, False, True, None, {}, []]
                for candidate in candidates:
                    assert Draft202012Validator(source).is_valid(candidate) == Draft202012Validator(sent).is_valid(candidate)
                seen.append(path)
            for key, value in source.items():
                if key == "properties":
                    for name, child in value.items():
                        remote = sent[key][name]
                        if name not in source.get("required", []):
                            remote = remote["anyOf"][0]
                        compare(child, remote, path + (key, name))
                elif key == "oneOf":
                    # Only disjoint discriminator/type unions may change spelling.
                    assert "oneOf" not in sent
                    compare(value, sent["anyOf"], path + ("anyOf",))
                elif key != "required":
                    if isinstance(value, (dict, list)):
                        compare(value, sent[key], path + (key,))
                    else:
                        assert sent[key] == value, path + (key,)
        elif isinstance(source, list):
            assert len(source) == len(sent)
            for index, (child, remote) in enumerate(zip(source, sent)):
                compare(child, remote, path + (index,))
        else:
            assert source == sent, path

    compare(local, provider)
    assert seen  # No fixed count: lossless finite-case expansion duplicates leaves.
    assert request == before
    assert wire["model"] == "gpt-6-sol"
    assert wire["text"]["format"]["type"] == "json_schema" and wire["text"]["format"]["strict"] is True
    if stage == "author":
        assert [item["role"] for item in wire["input"]] == ["developer", "user"]
        static, dynamic = [item["content"][0]["text"] for item in wire["input"]]
        # Only object member framing changed; restore the exact logical text.
        assert static[:-1] + "," + dynamic[1:] == request["messages"][1]["content"]
        assert set(json.loads(dynamic)) == {"recipeKey", "parents", "balanceCorridor"}
    else:
        assert [item["content"][0]["text"] for item in wire["input"]] == [
            item["content"] for item in request["messages"] if item["role"] != "system"
        ]
    assert local == (contract.author_item_response_schema() if stage == "author" else contract.author_item_repair_response_schema())


def _encode_nullable_fixture(value: Any, local: dict[str, Any]) -> Any:
    """Independent test encoder for valid sparse fixtures; never a production fallback."""
    from jsonschema import Draft202012Validator

    for union in ("oneOf", "anyOf"):
        if union in local:
            matches = [branch for branch in local[union] if Draft202012Validator(branch).is_valid(value)]
            assert len(matches) == 1
            return _encode_nullable_fixture(value, matches[0])
    if isinstance(value, dict):
        required = list(local.get("required", []))
        if "if" in local and Draft202012Validator(local["if"]).is_valid(value):
            required += local["then"]["required"]
        return {
            key: (_encode_nullable_fixture(value[key], child) if key in value else None)
            for key, child in local["properties"].items()
            if key in value or key not in required
        }
    if isinstance(value, list):
        return [_encode_nullable_fixture(child, local["items"]) for child in value]
    return copy.deepcopy(value)


def _sparse_event_item(fn, event):
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

    item = build_runtime_fixture("workbench_blade")
    calls = item["runtimeProgram"]["calls"]
    spawn = next(row for row in calls if row["fn"] == "spawn_entity_on_event")
    if fn == "spawn_entity_on_event":
        selected = spawn
    else:
        selected = {"id": "pull_case", "fn": fn, "target": spawn["target"],
                    "params": {"when": event, "mode": "target_to_entity", "strength": 1, "radiusTiles": 8}}
        calls.append(selected)
    selected["params"]["when"] = {"everyTicks": 6} if event == "periodic" else event
    next(row for row in calls if row["fn"] == "configure_item_stats")["params"].pop("manaCost", None)
    return item, selected


@pytest.mark.parametrize("stage", ["author", "repair"])
@pytest.mark.parametrize("fn", ["spawn_entity_on_event", "pull_on_event"])
@pytest.mark.parametrize("event", ["on_hit", "periodic"])
def test_subscription_nullable_roundtrip_uses_local_discriminators_across_subset_cases(stage, fn, event):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines import author_item_contract as contract
    from infini_local.core.runtime_authoring import validate_runtime_program

    item, selected = _sparse_event_item(fn, event)
    assert validate_runtime_program(item)["ok"]
    if stage == "author":
        local, provider = contract.author_item_response_schema(), contract.author_item_provider_response_schema()
        sparse = item
    else:
        local, provider = contract.author_item_repair_response_schema(), contract.author_item_provider_repair_response_schema()
        sparse = {"note": "exact event row", "callsUpsert": [selected], "realizationReplacement": item["realization"]}
    source = json.dumps(sparse, sort_keys=True)
    encoded = _encode_nullable_fixture(sparse, local)
    before = copy.deepcopy(encoded)
    assert Draft202012Validator(local).is_valid(sparse)
    assert Draft202012Validator(provider).is_valid(encoded)
    response_format = {"type": "json_schema", "json_schema": {"schema": provider}}
    restored = contract.project_provider_nullable_optionals_to_local(encoded, local, response_format=response_format)
    assert json.dumps(restored, sort_keys=True) == source
    assert json.dumps(sparse, sort_keys=True) == source and encoded == before


@pytest.mark.parametrize("fn", ["spawn_entity_on_event", "pull_on_event"])
def test_subscription_finite_event_cases_preserve_conditional_boundary_acceptance(fn):
    from jsonschema import Draft202012Validator
    from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
    from infini_local.pipelines import author_item_contract as contract

    local = CAPABILITY_REGISTRY[fn].provider_variant_schema()["properties"]["params"]
    provider = contract._provider_strict_projection(local)
    _, selected = _sparse_event_item(fn, "on_hit")
    valid_encoding = _encode_nullable_fixture(selected["params"], local)
    choices = [event for event in CAPABILITY_REGISTRY[fn].allowed_events if event != "periodic"]
    choices += ["unknown_event", "periodic", None, False, {}]
    choices += [{"everyTicks": period} for period in (None, False, 5, 6, 3600, 3601, 6.5, "6")]
    for when in choices:
        sparse = {**selected["params"], "when": when}
        encoded = {**valid_encoding, "when": when}
        source_valid = Draft202012Validator(local).is_valid(sparse)
        sent_valid = Draft202012Validator(provider).is_valid(encoded)
        assert source_valid == sent_valid, (fn, when)
        if isinstance(when, dict):
            period = when.get("everyTicks")
            assert sent_valid is (type(period) is int and 6 <= period <= 3600), when
    assert CAPABILITY_REGISTRY[fn].provider_variant_schema()["properties"]["params"] == local


@pytest.mark.parametrize("domain", ["bindings", "calls"])
def test_subscription_disjoint_union_preserves_registered_variants_and_adversarial_rejection(domain):
    from jsonschema import Draft202012Validator
    from infini_local.core.runtime_authoring.program_schema import binding_schema
    from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
    from infini_local.qa.capability_witnesses import build_capability_witness
    from infini_local.pipelines import author_item_contract as contract

    local = binding_schema() if domain == "bindings" else {"oneOf": [cap.provider_variant_schema() for cap in visible_capabilities()]}
    provider = contract._provider_strict_projection(local)
    assert len(provider["anyOf"]) == len(local["oneOf"])
    for branch in local["oneOf"]:
        if domain == "calls":
            fn = branch["properties"]["fn"]["const"]
            item = build_capability_witness(fn)
            row = next(call for call in item["runtimeProgram"]["calls"] if call["fn"] == fn)
            selector = "fn"
        else:
            input_kind = branch["properties"]["input"]["const"]
            action_kind = branch["properties"]["usePolicy"]["properties"]["action"]["properties"]["kind"]["const"]
            row = {"id": "binding_probe", "input": input_kind, "usePolicy": {
                "action": {"kind": action_kind, "targetId": "item"},
                "stackCost": 1 if action_kind == "place_item" else 0, "contactDamage": False}}
            if action_kind == "place_item":
                row["usePolicy"]["action"]["placementCallId"] = "place_call"
            selector = "input"
        assert Draft202012Validator(local).is_valid(row)
        encoded = _encode_nullable_fixture(row, branch)
        assert Draft202012Validator(provider).is_valid(encoded)
        controls = []
        for name, value in [(selector, "unknown"), ("id", "INVALID\r"), ("foreign", None)]:
            sparse_bad, sent_bad = copy.deepcopy(row), copy.deepcopy(encoded)
            sparse_bad[name] = sent_bad[name] = value
            controls.append((sparse_bad, sent_bad))
        sparse_bad, sent_bad = copy.deepcopy(row), copy.deepcopy(encoded)
        sparse_bad.pop(selector)
        sent_bad.pop(selector)
        controls.append((sparse_bad, sent_bad))
        for sparse_bad, sent_bad in controls:
            assert not Draft202012Validator(local).is_valid(sparse_bad), sparse_bad
            assert not Draft202012Validator(provider).is_valid(sent_bad), sent_bad
        if domain == "calls":
            for key, child in branch["properties"]["params"]["properties"].items():
                for limit, step in [("minimum", -1), ("maximum", 1)]:
                    if limit not in child:
                        continue
                    sparse_bad, sent_bad = copy.deepcopy(row), copy.deepcopy(encoded)
                    sparse_bad["params"][key] = sent_bad["params"][key] = child[limit] + step
                    assert not Draft202012Validator(local).is_valid(sparse_bad), (fn, key, limit)
                    assert not Draft202012Validator(provider).is_valid(sent_bad), (fn, key, limit)


@pytest.mark.parametrize("control", ["bad-neighbour", "required-null", "periodic-null", "unknown-event", "missing-event", "unknown-fn", "missing-fn", "array-null", "foreign-null", "different-wrapper", "reordered-provider"])
def test_subscription_inverse_never_hides_invalid_values_or_guesses_a_branch(control):
    from infini_local.pipelines import author_item_contract as contract, llm_authoring_pipeline as author

    item, _ = _sparse_event_item("pull_on_event", "on_hit")
    local, provider = contract.author_item_response_schema(), contract.author_item_provider_response_schema()
    encoded = _encode_nullable_fixture(item, local)
    call = next(row for row in encoded["runtimeProgram"]["calls"] if row["fn"] == "pull_on_event")
    params = call["params"]
    if control == "bad-neighbour":
        params["strength"] = "not a number"
    elif control == "required-null":
        params["strength"] = None
    elif control == "periodic-null":
        params["when"] = {"everyTicks": None}
    elif control == "unknown-event":
        params["when"] = "unknown_event"
    elif control == "missing-event":
        params.pop("when")
    elif control == "unknown-fn":
        call["fn"] = "unknown_function"
    elif control == "missing-fn":
        call.pop("fn")
    elif control == "array-null":
        encoded["runtimeProgram"]["calls"].insert(0, None)
    elif control == "foreign-null":
        params["foreign"] = None
    else:
        branches = provider["properties"]["runtimeProgram"]["properties"]["calls"]["items"]["anyOf"]
        if control == "reordered-provider":
            branches.reverse()
        else:
            case = next(branch for branch in branches if branch["properties"]["fn"]["const"] == "pull_on_event")["properties"]["params"]
            case["properties"]["delayTicks"] = case["properties"]["delayTicks"]["anyOf"][0]
    before = copy.deepcopy(encoded)
    response_format = {"type": "json_schema", "json_schema": {"schema": provider}}
    restored = author._prepare_parsed_author_item(encoded, response_format=response_format)
    rows = restored["runtimeProgram"]["calls"]
    restored_call = next(row for row in rows if isinstance(row, dict) and row.get("id") == "pull_case")
    if control in {"unknown-fn", "missing-fn"}:
        assert restored_call["params"] == params
    elif control == "different-wrapper":
        assert restored_call["params"]["delayTicks"] is None
    else:
        assert "delayTicks" not in restored_call["params"]
        if control == "periodic-null":
            assert restored_call["params"]["when"] == {"everyTicks": None}
        if control == "unknown-event":
            assert restored_call["params"]["when"] == "unknown_event"
        if control == "missing-event":
            assert "when" not in restored_call["params"]
        if control in {"bad-neighbour", "required-null"}:
            assert restored_call["params"]["strength"] == params["strength"]
        if control == "array-null":
            assert rows[0] is None and len(rows) == len(encoded["runtimeProgram"]["calls"])
        if control == "foreign-null":
            assert restored_call["params"]["foreign"] is None
    assert encoded == before
    assert contract.project_provider_author_item_to_local(encoded, response_format={"type": "json_object"}) == before
    from jsonschema import Draft202012Validator
    if control == "reordered-provider":
        assert json.dumps(restored, sort_keys=True) == json.dumps(item, sort_keys=True)
        assert Draft202012Validator(local).is_valid(restored)
    else:
        assert not Draft202012Validator(local).is_valid(restored), "inverse must not conceal an invalid authored value"


def test_subscription_repair_wire_inverse_precedes_frozen_merge(monkeypatch):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines import author_item_contract as contract, llm_authoring_pipeline as author
    from infini_local.core.runtime_authoring import validate_runtime_program

    item, selected = _sparse_event_item("pull_on_event", "periodic")
    expected = copy.deepcopy(item)
    selected["params"]["when"].pop("everyTicks")
    before = copy.deepcopy(item)
    failure = validate_runtime_program(item)
    assert not failure["ok"]
    corrected = copy.deepcopy(selected)
    corrected["params"].update(when={"everyTicks": 6}, strength=2)  # hostile valid sibling: must stay frozen at 1
    patch = {"note": "exact missing period", "callsUpsert": [corrected], "realizationReplacement": item["realization"]}
    encoded = _encode_nullable_fixture(patch, contract.author_item_repair_response_schema())
    monkeypatch.setattr(author, "USE_LLM", True)
    monkeypatch.setattr(author, "resolve_llm_model", lambda: "gpt-6-sol")
    monkeypatch.setattr(author, "trace_event", lambda *_a, **_kw: None)
    monkeypatch.setattr(llm, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    requests, premerge = [], []
    def respond(request, **_options):
        requests.append(copy.deepcopy(backend._request_payload(request)))
        assert Draft202012Validator(request["response_format"]["json_schema"]["schema"]).is_valid(encoded)
        return {"choices": [{"message": {"content": json.dumps(encoded)}}], "_debug": {"responseFormatType": "json_schema"}}
    original_filter = author.filter_repair_patch_scope
    def observe(current, delta, scope):
        premerge.append(copy.deepcopy(delta))
        assert scope["fieldPermissions"]["calls"] == [{"id": selected["id"], "paths": ["params.when.everyTicks"]}]
        return original_filter(current, delta, scope)
    monkeypatch.setattr(author, "llm_chat_json", respond)
    monkeypatch.setattr(author, "filter_repair_patch_scope", observe)
    repaired = author.repair_author_item_after_failure(item, {}, {}, {}, {}, "provider-offline", failure_report=failure)
    assert len(requests) == len(premerge) == 1
    _assert_structured_outputs_subset(requests[0]["text"]["format"]["schema"])
    assert requests[0]["model"] == "gpt-6-sol" and requests[0]["text"]["format"]["strict"] is True
    assert premerge == [patch]  # no null scaffolding reaches frozen-first Repair
    repaired.pop("debug", None)
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert item == before and validate_runtime_program(repaired)["ok"]


def test_subscription_primary_selection_type_union_keeps_string_constraints_and_null():
    from jsonschema import Draft202012Validator
    from infini_local.pipelines import author_item_contract as contract
    from infini_local.core.runtime_authoring.program_schema import PRIMARY_ENTITY_SELECTION_FIELD

    local = contract.author_item_repair_response_schema()["properties"][PRIMARY_ENTITY_SELECTION_FIELD]
    provider = contract._provider_strict_projection(local)
    assert set(provider) == {"anyOf"}
    for value in ["item", "blade_1", None, "", "Uppercase", "x" * 49, True, 1, 1.5, {}, []]:
        source_valid = Draft202012Validator(local).is_valid(value)
        assert source_valid is (value is None or value in ("item", "blade_1"))
        assert Draft202012Validator(provider).is_valid(value) is source_valid


@pytest.mark.parametrize("literal", [1, 1.0, 1.5, False, True, None, "exact", [1, "literal"], {"if": {"const": "not a schema"}}])
def test_subscription_const_types_preserve_jsonschema_numeric_and_literal_domains(literal):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines import author_item_contract as contract

    source = {"const": literal}
    provider = contract._provider_strict_projection(source)
    assert provider["const"] == literal and source == {"const": literal}
    if type(literal) is float:
        assert provider["type"] == "number"  # 1.5 must not be narrowed to integer
    for candidate in [literal, 0, 1, 1.0, 1.5, False, True, None, "other", {}, []]:
        assert Draft202012Validator(source).is_valid(candidate) == Draft202012Validator(provider).is_valid(candidate)


@pytest.mark.parametrize("shape", ["overlapping-union", "optional-selector", "optional-ancestor", "numeric-overlap", "type-overlap", "non-finite-const", "conditional-optional-selector", "conditional-unbounded-selector", "conditional-predicate", "conditional-consequent", "conditional-unknown-addition", "conditional-else", "allOf", "not", "dependentRequired", "dependentSchemas"])
def test_subscription_projection_rejects_unproved_future_compositions(shape):
    from infini_local.pipelines import author_item_contract as contract
    from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY

    branch = {"type": "object", "properties": {"tag": {"const": "a"}}, "required": ["tag"], "additionalProperties": False}
    opposite = copy.deepcopy(branch)
    opposite["properties"]["tag"]["const"] = "b"
    source = {"oneOf": [branch, opposite]}
    if shape == "overlapping-union":
        opposite["properties"]["tag"]["const"] = "a"
    elif shape == "optional-selector":
        branch["required"] = opposite["required"] = []
    elif shape == "optional-ancestor":
        source = {"oneOf": [{"type": "object", "properties": {"nested": row}, "additionalProperties": False} for row in [branch, opposite]]}
    elif shape == "numeric-overlap":
        branch["properties"]["tag"]["const"] = 1
        opposite["properties"]["tag"]["const"] = 1.0
    elif shape == "type-overlap":
        source = {"oneOf": [{"type": "integer"}, {"type": "number"}]}
    elif shape == "non-finite-const":
        source = {"const": float("nan")}
    elif shape.startswith("conditional-"):
        source = {"type": "object", "additionalProperties": False,
                  "properties": {"event": {"type": "string", "enum": ["on_hit", "periodic"]},
                                 "periodTicks": {"type": "integer", "minimum": 6},
                                 "delayTicks": {"type": "integer", "minimum": 0}},
                  "required": ["event"],
                  "if": {"properties": {"event": {"const": "periodic"}}, "required": ["event"]},
                  "then": {"required": ["periodTicks"]}}
        if shape == "conditional-optional-selector":
            source["required"].remove("event")
        elif shape == "conditional-unbounded-selector":
            source["properties"]["event"].pop("enum")
        elif shape == "conditional-predicate":
            source["if"]["properties"]["event"] = {"pattern": "periodic"}
        elif shape == "conditional-consequent":
            source["then"]["properties"] = {"periodTicks": {"minimum": 10}}
        elif shape == "conditional-unknown-addition":
            source["then"]["required"] = ["new_mechanic"]
        else:
            source["else"] = {"required": ["delayTicks"]}
    else:
        source = {shape: {} if shape != "allOf" else [branch]}
    before = copy.deepcopy(source)
    with pytest.raises(ValueError, match="Unproved provider"):
        contract._provider_strict_projection(source)
    assert source.keys() == before.keys()
    if shape != "non-finite-const":
        assert source == before


def message(text, *, phase=None, **extra):
    result = {"type": "message", "role": "assistant", "status": "completed",
              "content": [{"type": "output_text", "text": text}], **extra}
    if phase is not None:
        result["phase"] = phase
    return result


def token_response():
    claims = {"exp": int(time.time()) + 3600, "https://api.openai.com/auth": {"chatgpt_account_id": "test-account"}}
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return {"access_token": "test." + body + ".unsigned", "refresh_token": "test-refresh-not-real", "expires_in": 3600}


@pytest.fixture
def subscription(monkeypatch):
    credentials = auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account", 9999999999)
    response = {"status": "completed", "output": [message('{"ok":true}')]}
    monkeypatch.setattr(auth, "get_credentials", lambda: credentials)
    monkeypatch.setattr(auth, "post_sse", lambda *_a, **_k: copy.deepcopy(response))
    return response, credentials


@dataclass
class StreamOpener:
    body: bytes
    requests: list = field(default_factory=list)

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return io.BytesIO(self.body)


@pytest.mark.parametrize("callback,valid", [("valid", True), ("wrong-state", False), ("duplicate-state", False), ("duplicate-code", False)])
def test_pkce_callback_binds_state_and_rejects_duplicates(callback, valid):
    attempt = auth.LoginAttempt()
    params = parse_qs(urlsplit(attempt.authorization_url).query)
    expected = base64.urlsafe_b64encode(hashlib.sha256(attempt.verifier.encode()).digest()).decode().rstrip("=")
    assert params["code_challenge"] == [expected] and params["code_challenge_method"] == ["S256"]
    assert params["redirect_uri"] == ["http://localhost:1455/auth/callback"]
    assert params["scope"] == ["openid profile email offline_access"]
    assert attempt.verifier not in repr(attempt)
    suffix = {"valid": f"state={attempt.state}&code=test-code", "wrong-state": "state=wrong&code=x",
        "duplicate-state": f"state={attempt.state}&state=wrong&code=x", "duplicate-code": f"state={attempt.state}&code=x&code=y"}[callback]
    if valid:
        assert attempt.callback_code("/auth/callback?" + suffix) == "test-code"
    else:
        with pytest.raises(auth.CodexError):
            attempt.callback_code("/auth/callback?" + suffix)


@pytest.mark.parametrize("method,status,encoding,diagnostic", [
    pytest.param("post", 429, "plain", "quota reached", id="post-status-and-redaction"),
    pytest.param("get", 403, "twice-unicode", "quota", id="twice-escaped-credential"),
    pytest.param("get", 403, "nested-unicode", "quota", id="nested-escaped-credential"),
    pytest.param("get", 400, "diagnostic-code", "unsupported_parameter", id="non-message-diagnostic"),
])
def test_auth_http_diagnostics_keep_status_not_credentials(monkeypatch, method, status, encoding, diagnostic):
    secret = "test-access-not-real"
    twice = ''.join(r'\\u%04x' % ord(char) for char in secret)
    if encoding == "twice-unicode":
        assert auth._decode_unicode_runs(twice) == secret
    echoed = secret if encoding == "plain" else twice if encoding == "twice-unicode" else '{"token":"' + ''.join(r'\u%04x' % ord(char) for char in secret) + '"}'
    body = {"error": {"code": "unsupported_parameter", "param": "stream"}} if encoding == "diagnostic-code" else {"error": {"message": diagnostic + " " + echoed}}
    url = CODEX + ("/images/generations" if method == "post" else "/models")
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == url
            if method == "post":
                assert request.get_header("User-agent") == "infinicrafter/1.0"
            raise HTTPError(request.full_url, status, "denied", {}, io.BytesIO(json.dumps(body).encode()))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_: Opener())
    with pytest.raises(auth.CodexError) as caught:
        if method == "post":
            auth.post_json(url, {}, headers={"Authorization": "Bearer " + secret})
        else:
            auth.get_json(url, headers={"Authorization": "Bearer " + secret})
    error = str(caught.value)
    assert f"HTTP {status}" in error and diagnostic in error
    assert secret not in error.replace('\\', '')
    assert "\\u" not in error


@pytest.mark.parametrize("scenario,expected,error", [
    pytest.param("commentary-and-final", '{"item":"Клинок"}', None, id="commentary-not-authored"),
    pytest.param("commentary-only", None, "text output", id="commentary-only-refused"),
    pytest.param("in_progress", None, "incomplete", id="unfinished-final"),
    pytest.param("incomplete", None, "incomplete", id="incomplete-final"),
    pytest.param("legacy-parts", '{"label":"Клинок"}', None, id="legacy-split-text"),
    pytest.param("final-parts", '{"label":"Клинок"}', None, id="final-split-text"),
    pytest.param("refusal", None, "refused", id="final-refusal-after-text"),
])
def test_subscription_output_selects_only_completed_final_authored_text(scenario, expected, error):
    if scenario == "commentary-and-final":
        output = [message("I will validate the item first.\n", phase="commentary"), {"type": "reasoning", "summary": []}, message(expected, phase="final_answer")]
    elif scenario == "commentary-only":
        output = [message('{"status":"working"}', phase="commentary")]
    elif scenario in {"in_progress", "incomplete"}:
        output = [message('{"partial":', phase="final_answer", status=scenario)]
    elif scenario == "refusal":
        item = message('{"ok":true}', phase="final_answer")
        item["content"].append({"type": "refusal", "refusal": "test refusal"})
        output = [item]
    else:
        item = message("", phase="final_answer" if scenario == "final-parts" else None)
        item.pop("status")
        item["content"] = [{"type": "output_text", "text": '{"label":'}, {"type": "output_text", "text": '"Клинок"}'}]
        output = [item]
    response = {"output": output}
    before = copy.deepcopy(response)
    if error:
        with pytest.raises(auth.CodexError, match=error):
            backend._output_text(response)
    else:
        text = backend._output_text(response)
        assert text == expected and json.loads(text) == json.loads(expected)
    assert response == before


@pytest.mark.parametrize("encoding,commentary", [
    pytest.param("unicode", False, id="legacy-escaped-credential"),
    pytest.param("unicode", True, id="final-escaped-credential"),
    pytest.param("twice-unicode", False, id="twice-escaped-text-credential"),
])
def test_subscription_rejects_encoded_credential_echo(subscription, encoding, commentary):
    response, credentials = subscription
    echo = r'\u0074est-access-not-real' if encoding == "unicode" else ''.join(r'\\u%04x' % ord(char) for char in credentials.access_token)
    response["output"] = ([message("Preparing an answer.", phase="commentary")] if commentary else []) + [message('{"nested":"' + echo + '"}', phase="final_answer" if commentary else None)]
    with pytest.raises(auth.CodexError, match="credential") as caught:
        backend.generate_chat({"model": "test-model", "messages": [{"role": "user", "content": "test"}]}, timeout=3)
    assert credentials.access_token not in str(caught.value)


@pytest.mark.parametrize("present,value", [(False, None), (True, 168), *[(True, x) for x in [True, -1, 1.5, "168", None, [], {}]]])
def test_subscription_cache_instruction_attribution_survives_usage_projection(subscription, present, value, monkeypatch, tmp_path):
    response, credentials = subscription
    response["usage"] = {"input_tokens": 22000, "output_tokens": 120,
        "input_tokens_details": {"cached_tokens": 21000}, "output_tokens_details": {"reasoning_tokens": 100}}
    if present:
        response["usage"]["attribution"] = {"request_fields": {"instructions": {
            "input_tokens": value, "cached_tokens": value, "cache_write_tokens": 0, "output_tokens": 0,
            "metadata": credentials.access_token,
        }}, "items": {credentials.refresh_token: {"input_tokens": 10}}}
    result = backend.generate_chat({"model": "gpt-6.1-sol", "messages": [{"role": "user", "content": "test"}]}, timeout=3)
    diagnostic = llm._usage_fields(result)
    assert diagnostic["reasoningTokens"] == 100
    assert diagnostic["instructionsInputTokens"] == (value if present and type(value) is int and value >= 0 else None)
    assert diagnostic["instructionsCachedInputTokens"] == (value if present and type(value) is int and value >= 0 else None)
    assert diagnostic["instructionsCacheWriteTokens"] == (0 if present else None)
    assert credentials.access_token not in repr(result) and credentials.refresh_token not in repr(result)
    from infini_local.storage import trace_runtime
    monkeypatch.setattr(trace_runtime, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    llm.log_event("info", "LLM usage", diagnostic)
    persisted = json.loads((tmp_path / "events.ndjson").read_text())["payload"]
    assert persisted == diagnostic
    assert credentials.access_token not in repr(persisted) and credentials.refresh_token not in repr(persisted)


@pytest.mark.parametrize("scenario,value", [
    pytest.param("full", None, id="safe-usage-whitelist"),
    pytest.param("metadata", None, id="provider-metadata-removed"),
    *[pytest.param("counter", value, id=f"counter-{index}") for index, value in enumerate([0, 7, True, False, -1, 1.5, "20", None, {}, []])],
    *[pytest.param("container", value, id=f"container-{index}") for index, value in enumerate([None, [], "metadata", 5])],
    pytest.param("cache-write", None, id="cache-write-preserved"),
    pytest.param("missing", None, id="missing-cache-is-not-zero"),
])
def test_subscription_usage_is_typed_whitelisted_and_preserved_through_transport(subscription, scenario, value):
    response, credentials = subscription
    if scenario == "full":
        response["usage"] = {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150,
            "input_tokens_details": {"cached_tokens": 100, "metadata": credentials.access_token},
            "output_tokens_details": {"reasoning_tokens": 20, "metadata": credentials.refresh_token}, "attribution": credentials.account_id}
        expected = {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150, "input_tokens_details": {"cached_tokens": 100}, "output_tokens_details": {"reasoning_tokens": 20}}
    elif scenario == "metadata":
        response["id"] = credentials.access_token
        response["usage"] = {"input_tokens": 3, "output_tokens": 5, "attribution": {"secret": credentials.access_token}}
        expected = {"input_tokens": 3, "output_tokens": 5}
    elif scenario == "counter":
        response["usage"] = {"input_tokens_details": {"cached_tokens": value}, "output_tokens_details": {"reasoning_tokens": value}}
        expected = response["usage"] if type(value) is int and value >= 0 else {}
    elif scenario == "container":
        response["usage"] = {"input_tokens": 2, "input_tokens_details": value, "output_tokens_details": value}
        expected = {"input_tokens": 2}
    elif scenario == "cache-write":
        response["usage"] = {"input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 30, "not_a_counter": "private"}}
        expected = {"input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 30}}
    else:
        response["usage"] = {"input_tokens": 7}
        expected = {"input_tokens": 7}
    context = {"provider": "openai_codex", "base_url": CODEX, "model": "test-model", "api_mode": "responses", "api_key": ""}
    result = llm._llm_json_single_context(packet(), 3, context)
    assert result["usage"] == expected
    if scenario == "missing":
        assert result["_debug"]["cachedInputTokens"] is None and result["_debug"]["cacheHit"] is None
    for secret in (credentials.access_token, credentials.refresh_token, credentials.account_id):
        assert secret not in repr(result)


@pytest.mark.parametrize("scenario", ["inline-phases", "done-item-phases", "completed-done-item", "completed-event", "partial-no-completion"])
def test_actual_sse_parser_requires_completion_and_preserves_final_phase(monkeypatch, scenario):
    credentials = auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account", 9999999999)
    monkeypatch.setattr(auth, "get_credentials", lambda: credentials)
    items = [message("First I will inspect the schema.\n", phase="commentary"), message('{"ok":true}', phase="final_answer")]
    completion = {"id": "resp-test", "status": "completed", "usage": {"input_tokens_details": {"cached_tokens": 42}}}
    if scenario.startswith("inline"):
        completion["output"] = items
    events = [{"type": "response.output_item.done", "item": item} for item in items]
    if scenario == "completed-done-item":
        events = [{"type": "response.output_item.done", "item": message("final")}]
        completion["output"] = []
    elif scenario in {"completed-event", "partial-no-completion"}:
        events = [{"type": "response.output_text.delta", "delta": "partial"}]
        completion["output"] = [message("complete")]
    if scenario != "partial-no-completion":
        events.append({"type": "response.completed", "response": completion})
    opener = StreamOpener(b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *_: opener)
    if scenario == "partial-no-completion":
        with pytest.raises(auth.CodexError, match="before completion"):
            auth.post_sse(backend.RESPONSES_URL, {"stream": True})
    elif scenario.endswith("phases"):
        result = backend.generate_chat({"model": "test-model", "messages": [{"role": "user", "content": "test"}]}, timeout=3)
        assert result["choices"][0]["message"]["content"] == '{"ok":true}'
        assert result["usage"] == {"input_tokens_details": {"cached_tokens": 42}}
    else:
        result = auth.post_sse(backend.RESPONSES_URL, {"stream": True}, headers={"Authorization": "Bearer test-access-not-real"})
        assert result["id"] == "resp-test"
        assert result["output"][0]["content"][0]["text"] == ("final" if scenario == "completed-done-item" else "complete")
    assert len(opener.requests) == 1
    assert opener.requests[0][0].full_url == backend.RESPONSES_URL
    assert opener.requests[0][0].get_header("Accept") == "text/event-stream"


@pytest.mark.parametrize("source", ["primary", "pool", "fallback"])
def test_subscription_profile_cannot_adopt_paid_platform_endpoint_or_key(wire, monkeypatch, source):
    wire.configure(LLM_PROVIDER="openai_codex" if source == "primary" else "local", CODEX_LLM_MODEL="test-model",
        OPENAI_COMPAT_BASE_URL="https://api.openai.com/v1", OPENAI_COMPAT_API_KEY="test-platform-key-not-real",
        LLM_FALLBACK_PROVIDER="openai_codex", LLM_FALLBACK_MODEL="test-model", LLM_FALLBACK_BASE_URL="https://api.openai.com/v1",
        LLM_FALLBACK_API_KEY="test-paid-key-not-real")
    if source == "primary":
        context = llm._legacy_primary_llm_context()
    elif source == "fallback":
        context = llm._fallback_llm_context()
    else:
        context = llm._pool_profile_context({"id": "llm_2", "enabled": True, "provider": "openai_codex", "model": "test-model",
            "base_url": "https://api.openai.com/v1", "api_key": "test-platform-key-not-real", "api_mode": "chat_completions", "openrouter_provider": PIN})
    assert context is not None
    assert (context["provider"], context["model"], context["base_url"], context["api_key"], context["api_mode"]) == ("openai_codex", "test-model", CODEX, "", "responses")
    assert llm.llm_responses_url({**context, "base_url": "https://api.openai.com/v1"}) == CODEX + "/responses"
    assert llm.llm_models_url(context) == catalog.MODELS_URL + "?client_version=" + catalog.CLIENT_VERSION
    with pytest.raises(auth.CodexError):
        llm.llm_chat_completions_url(context)
    if source == "primary":
        monkeypatch.setattr(auth, "auth_status", lambda: {"authenticated": False, "expired": False})
        snapshot = llm.llm_auth_snapshot()
        assert (snapshot["provider"], snapshot["status"], snapshot["apiKeyConfigured"]) == ("openai_codex", "sign_in_required", None)
        assert "api.openai.com" not in str(snapshot)


@pytest.mark.parametrize("scenario,override", [("success", None), ("success", "codex-visual-override"), ("failure", "codex-visual-override")])
def test_subscription_dispatch_strips_foreign_pin_and_never_pays_for_fallback(wire, monkeypatch, subscription, scenario, override):
    response, credentials = subscription
    wire.configure(LLM_PROVIDER="openai_codex", CODEX_LLM_MODEL="test-model", CODEX_VISUAL_REASONING="low",
        LLM_FALLBACK_PROVIDER="openrouter", LLM_FALLBACK_MODEL="paid-route-not-authorized", LLM_FALLBACK_OPENROUTER_PROVIDER=PIN)
    calls, prepared_calls = [], []
    generate = backend.generate_chat
    monkeypatch.setattr(backend, "generate_chat", lambda payload, timeout: prepared_calls.append(copy.deepcopy(payload)) or generate(payload, timeout=timeout))
    def post(url, body, **options):
        calls.append((url, copy.deepcopy(body), options))
        if scenario == "failure":
            raise auth.CodexError("OpenAI HTTP 429: quota")
        return response
    monkeypatch.setattr(auth, "post_sse", post)
    monkeypatch.setattr(llm, "http_json", lambda *_a, **_k: pytest.fail("paid/legacy HTTP called"))
    request = packet("visual_director")
    request["provider"] = {"only": [PIN], "allow_fallbacks": False}
    request["reasoning"] = {"effort": "high"}
    if override:
        request[llm.LLM_MODEL_OVERRIDE_KEY] = override
    if scenario == "failure":
        with pytest.raises(auth.CodexError, match="429"):
            llm.llm_chat_json(request, timeout=3)
    else:
        result = llm.llm_chat_json(request, timeout=3)
        assert result["choices"][0]["message"]["content"] == '{"ok":true}'
        url, body, options = calls[0]
        assert url == CODEX + "/responses" and body["model"] == (override or "test-model")
        assert body["reasoning"] == {"effort": "low"}
        assert body["instructions"] == request["messages"][0]["content"]
        assert body["input"] == [
            {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "JSON response."}]},
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": request["messages"][1]["content"]}]},
        ]
        assert "provider" not in body and llm.LLM_MODEL_OVERRIDE_KEY not in body
    assert len(calls) == len(prepared_calls) == 1
    assert "provider" not in prepared_calls[0] and llm.LLM_MODEL_OVERRIDE_KEY not in prepared_calls[0]
    assert prepared_calls[0]["model"] == (override or "test-model")


@pytest.mark.parametrize("scenario", ["literal-stage", "assistant-history", "untranslatable-budget"])
def test_subscription_request_preserves_packet_and_only_supported_wire_options(monkeypatch, subscription, scenario):
    request = {"model": "test-codex-model", "messages": [{"role": "system", "content": "Literal system contract"},
        {"role": "user", "content": "Literal authored item"}], "max_tokens": 2048,
        "response_format": {"type": "json_object"}, "reasoning": {"effort": "low", "exclude": True}, "temperature": 0.38}
    if scenario == "assistant-history":
        request["messages"] = [{"role": "system", "content": "Literal system contract"},
            {"role": "developer", "content": "Literal developer contract"}, {"role": "user", "content": "First request"},
            {"role": "assistant", "content": '{"old":"Клинок"}'}, {"role": "user", "content": "Repair only the invalid field."}]
    if scenario == "untranslatable-budget":
        request["reasoning"] = {"max_tokens": 1500}
        with pytest.raises(auth.CodexError, match="reasoning"):
            backend._request_payload(request)
        return
    response, credentials = subscription
    response["output"] = [message('{"item":"ok"}')]
    response["usage"] = {"input_tokens": 10, "output_tokens": 4}
    calls = []
    monkeypatch.setattr(auth, "post_sse", lambda url, body, **options: calls.append((url, body, options)) or response)
    before = copy.deepcopy(request)
    result = backend.generate_chat(request, timeout=20)
    assert request == before and result["choices"][0]["message"]["content"] == '{"item":"ok"}'
    assert result["usage"]["output_tokens"] == 4 and len(calls) == 1
    url, body, options = calls[0]
    assert url == CODEX + "/responses" and body["model"] == "test-codex-model"
    assert body["instructions"] == "Literal system contract"
    assert body["input"] == [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "JSON response."}]}] + [{"type": "message", "role": item["role"], "content": [{
        "type": "output_text" if item["role"] == "assistant" else "input_text", "text": item["content"]}]} for item in request["messages"][1:]]
    assert body["reasoning"] == {"effort": "low"} and body["text"]["format"] == {"type": "json_object"}
    assert body["stream"] is True and body["store"] is False and body["tools"] == []
    assert "max_output_tokens" not in body and "temperature" not in body
    assert options["headers"]["Authorization"] == "Bearer " + credentials.access_token
    assert options["headers"]["ChatGPT-Account-Id"] == credentials.account_id


@pytest.mark.parametrize("stage,configured,expected", [("visual_director", "high", "low"), ("planner", "high", "high"), ("planner", "max", "max")])
def test_subscription_reasoning_respects_stage_owner_and_catalog_max(wire, monkeypatch, stage, configured, expected):
    wire.configure(LLM_PROVIDER="openai_codex", LLM_REASONING_MODE=configured, CODEX_VISUAL_REASONING="low")
    context = {"provider": "openai_codex", "model": "gpt-6-sol", "base_url": CODEX, "api_mode": "responses", "api_key": ""}
    reasoning = llm.llm_reasoning_payload("gpt-6-sol", context)
    assert reasoning is not None and reasoning["effort"] == configured
    prepared = llm._payload_for_context({"messages": [{"role": "user", "content": "test"}], "reasoning": reasoning, llm.LLM_STAGE_KEY: stage}, context)
    assert prepared["reasoning"]["effort"] == expected
    if configured == "max":
        assert llm.apply_minimum_reasoning_effort({"reasoning": reasoning}, model_name="gpt-6-sol", minimum="medium")["reasoning"]["effort"] == "max"


def test_account_catalog_protocol_discovers_newly_gated_models(monkeypatch, subscription):
    # Offline transport fixture for the observed client-version gate, not a
    # synthesized production model list or an inference entitlement assertion.
    calls = []
    rows = [
        {"slug": "gpt-6-sol", "visibility": "list", "priority": 1},
        {"slug": "gpt-6.1-sol", "visibility": "list", "priority": 0,
         "supported_reasoning_levels": [{"effort": "low"}, {"effort": "high"}],
         "default_reasoning_level": "low"},
    ]

    def get(url, **options):
        calls.append((url, options))
        version = parse_qs(urlsplit(url).query)["client_version"][0]
        return {"models": rows if tuple(map(int, version.split("."))) >= (0, 161, 0) else rows[:1]}

    monkeypatch.setattr(auth, "get_json", get)
    models = catalog.list_text_models()
    assert [model.slug for model in models] == ["gpt-6.1-sol", "gpt-6-sol"]
    assert models[0].efforts == ("low", "high")
    assert models[0].default_effort == "low"
    assert len(calls) == 1
    assert urlsplit(calls[0][0]).netloc == "chatgpt.com"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer test-access-not-real"


@pytest.mark.parametrize("scenario", ["visible", "credential-metadata", "empty"])
def test_account_catalog_preserves_declared_models_and_rejects_unsafe_metadata(monkeypatch, subscription, scenario):
    _, credentials = subscription
    if scenario == "visible":
        rows = [{"slug": "hidden-model", "display_name": "Hidden", "visibility": "hide", "priority": 0},
            {"slug": "model-high", "display_name": "High", "visibility": "list", "priority": 10, "supported_in_api": False,
             "default_reasoning_level": "low", "supported_reasoning_levels": [{"effort": "low", "description": "Low"}, {"effort": "high", "description": "High"}]},
            {"slug": "model-first", "display_name": "First", "visibility": "list", "priority": 1, "supported_reasoning_levels": [{"effort": "medium", "description": "Medium"}]},
            {"slug": "model-first", "display_name": "Duplicate", "visibility": "list", "priority": 2}]
    elif scenario == "credential-metadata":
        rows = [{"slug": credentials.access_token, "visibility": "list", "display_name": "unsafe"},
            {"slug": "gpt-safe", "visibility": "list", "display_name": "echo " + credentials.access_token,
             "supported_reasoning_levels": [{"effort": credentials.access_token}, {"effort": "low"}], "default_reasoning_level": credentials.access_token}]
    else:
        rows = [{"slug": "", "visibility": "list"}]
    captured = []
    monkeypatch.setattr(auth, "get_json", lambda url, **options: captured.append((url, options)) or {"models": rows})
    if scenario == "empty":
        with pytest.raises(auth.CodexError):
            catalog.list_text_models()
    else:
        models = catalog.list_text_models()
        assert [item.slug for item in models] == (["model-first", "model-high"] if scenario == "visible" else ["gpt-safe"])
        selected = models[-1]
        assert selected.efforts == (("low", "high") if scenario == "visible" else ("low",))
        assert selected.default_effort == ("low" if scenario == "visible" else "")
        if scenario == "credential-metadata":
            assert selected.label == "gpt-safe" and credentials.access_token not in repr(models)
    assert len(captured) == 1 and captured[0][0] == catalog.MODELS_URL + "?client_version=" + catalog.CLIENT_VERSION
    assert captured[0][1]["headers"]["Authorization"] == "Bearer test-access-not-real"
    assert captured[0][1]["headers"]["ChatGPT-Account-Id"] == credentials.account_id
    assert "api.openai.com" not in captured[0][0]


def test_expired_session_refreshes_once_under_concurrent_requests(tmp_path, monkeypatch):
    assert hasattr(auth, "get_credentials"), "OAuth refresh is missing"
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    path = tmp_path / "codex-auth.json"
    fresh = auth.credentials_from_response(token_response())
    auth.save_credentials(replace(fresh, expires_at=1), path)
    calls = []
    def post(url, payload, **kwargs):
        calls.append((url, payload))
        return {**token_response(), "refresh_token": "test-rotated-not-real"}
    monkeypatch.setattr(auth, "post_json", post)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda _: auth.get_credentials(path), range(4)))
    assert len(calls) == 1
    assert calls[0][0] == "https://auth.openai.com/oauth/token"
    assert calls[0][1]["grant_type"] == "refresh_token"
    assert all(c.refresh_token == "test-rotated-not-real" for c in values)
    assert auth.load_credentials(path) == values[0]


def test_browser_login_exchanges_pkce_once_and_saves_only_after_callback(tmp_path, monkeypatch):
    assert hasattr(auth, "login"), "browser callback login is missing"
    import threading
    from urllib.request import urlopen
    from urllib.error import HTTPError
    path = tmp_path / "codex-auth.json"
    calls, threads, callback_results = [], [], []
    def post(url, payload, **kwargs):
        calls.append(payload)
        assert payload["grant_type"] == "authorization_code"
        assert payload["code"] == "test-code"
        assert len(payload["code_verifier"]) >= 43
        return token_response()
    monkeypatch.setattr(auth, "post_json", post)
    def visit(url):
        assert not path.exists()
        params = parse_qs(urlsplit(url).query)
        callback = params["redirect_uri"][0]
        def send():
            try:
                urlopen(callback + "?state=wrong&code=test-code", timeout=5)
            except HTTPError as exc:
                callback_results.append(exc.code)
            with urlopen(callback + "?state=" + params["state"][0] + "&code=test-code", timeout=5) as response:
                callback_results.append(response.status)
        thread = threading.Thread(target=send)
        threads.append(thread)
        thread.start()
    auth.login(path=path, on_url=visit, open_browser=False, port=0, timeout=10)
    for thread in threads:
        thread.join(5)
    assert callback_results == [400, 200]
    assert len(calls) == 1
    assert auth.auth_status(path)["authenticated"]


def test_authorization_code_exchange_uses_native_form_encoding(monkeypatch):
    import io
    class Response(io.BytesIO):
        pass
    class Opener:
        def open(self, request, timeout):
            assert request.get_header("Content-type") == "application/x-www-form-urlencoded"
            assert parse_qs(request.data.decode()) == {"code": ["test+code"], "grant_type": ["authorization_code"]}
            return Response(b'{"ok": true}')
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    assert auth.post_json(auth.TOKEN_URL, {"code": "test+code", "grant_type": "authorization_code"}, form=True) == {"ok": True}


def test_sse_rejects_late_completion_and_bounds_each_socket_read(monkeypatch):
    import io
    event = b'data: {"type":"response.completed","response":{"status":"completed","output":[]}}\n\n'
    socket_limits = []
    class Socket:
        def settimeout(self, value):
            socket_limits.append(value)
    class Response(io.BytesIO):
        def __init__(self):
            super().__init__(event)
            from types import SimpleNamespace
            self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=Socket()))
        def readline(self, *args, **kwargs):
            time.sleep(0.04)
            return super().readline(*args, **kwargs)
    class Opener:
        def open(self, request, timeout):
            return Response()
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    with pytest.raises(auth.CodexError, match="timed out"):
        auth.post_sse("https://chatgpt.com/backend-api/codex/responses", {"stream": True}, timeout=0.02)
    assert socket_limits and all(0 < value <= 0.02 for value in socket_limits)


def test_bounded_catalog_get_uses_only_codex_origin_and_redacts_errors(monkeypatch):
    import io
    from email.message import Message
    from urllib.error import HTTPError
    key = "test-access-not-real"
    requests = []
    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert timeout == 3
            if len(requests) == 1:
                return io.BytesIO(b'{"models": []}')
            raise HTTPError(request.full_url, 403, "denied", Message(), io.BytesIO(json.dumps({"error": {"message": "denied " + key}}).encode()))
    monkeypatch.setattr(auth.urlrequest, "build_opener", lambda *a: Opener())
    url = "https://chatgpt.com/backend-api/codex/models?client_version=0.4.241"
    headers = {"Authorization": "Bearer " + key}
    assert auth.get_json(url, headers=headers, timeout=3, limit=128) == {"models": []}
    assert requests[0].get_method() == "GET"
    with pytest.raises(auth.CodexError, match="HTTP 403") as caught:
        auth.get_json(url, headers=headers, timeout=3, limit=128)
    assert key not in str(caught.value)
    with pytest.raises(auth.CodexError):
        auth.get_json("https://api.openai.com/v1/models", headers=headers)


def test_native_session_roundtrip_is_private_and_status_has_no_secrets(tmp_path):
    path = tmp_path / "codex-auth.json"
    credentials = auth.credentials_from_response(token_response())
    auth.save_credentials(credentials, path)
    loaded = auth.load_credentials(path)
    assert loaded == credentials
    assert credentials.access_token not in repr(credentials)
    status = auth.auth_status(path)
    assert status == {"authenticated": True, "expired": False}
    assert "test-refresh" not in json.dumps(status)
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    auth.logout(path)
    assert auth.auth_status(path) == {"authenticated": False, "expired": False}


@pytest.mark.parametrize("color,remove_bg,mode,background", [
    ("magenta", True, "sprite_keyer", "opaque"),
    ("white", True, "sprite_keyer", "opaque"),
    ("transparent", True, "sprite_keyer", "transparent"),
    ("transparent", False, "sprite_keyer", "transparent"),
    ("cyan", False, "sprite_keyer", "transparent"),
    ("magenta", True, "off", "transparent"),
])
def test_codex_dispatch_writes_verified_png_and_preserves_authored_prompt(tmp_path, monkeypatch, color, remove_bg, mode, background):
    from infini_local.pipelines import pipeline_visual_config as visual_config
    monkeypatch.setattr(visual_config, "BG_COLOR", color)
    monkeypatch.setattr(visual_config, "REMOVE_BG", remove_bg)
    monkeypatch.setattr(visual_config, "BG_REMOVE_MODE", mode)
    assert "openai_codex" in config.SUPPORTED_IMAGE_BACKENDS
    assert config.IMAGE_BACKEND_ALIASES.get("openai_codex", "openai_codex") != "image_api"
    import base64
    import contextlib
    import io
    import time
    from PIL import Image
    from infini_local.pipelines import image_backend_pipeline as backend, visual_sprite_generation as visual
    from infini_local.services import codex_auth as auth
    assert hasattr(backend, "generate_openai_codex"), "Codex is not connected to sprite dispatch"
    stream = io.BytesIO()
    Image.new("RGBA", (64, 64), (15, 120, 240, 255)).save(stream, format="PNG")
    calls, gate = [], []
    credentials = auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account", time.time() + 3600)
    monkeypatch.setattr(auth, "get_credentials", lambda: credentials)
    def post(url, payload, **kwargs):
        assert gate == ["entered"]
        calls.append((url, payload, kwargs))
        return {"data": [{"b64_json": base64.b64encode(stream.getvalue()).decode()}]}
    monkeypatch.setattr(auth, "post_json", post)
    monkeypatch.setattr(backend, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(backend, "GENERATE_VARIANTS", 1)
    monkeypatch.setattr(visual, "IMAGE_BACKEND", "openai_codex")
    monkeypatch.setattr(visual, "IMAGE_BACKEND_CONFIG_ERROR", "")
    class Gate:
        @contextlib.contextmanager
        def slot(self):
            gate.append("entered")
            yield
            gate.append("exited")
    monkeypatch.setattr(visual, "IMAGE_GENERATION_GATE", Gate())
    for name in ("generate_image_api", "generate_sdcpp"):
        monkeypatch.setattr(visual, name, lambda *a: (_ for _ in ()).throw(AssertionError("unexpected fallback")))
    paths = visual._generate_backend_variants({}, prompt="Literal authored предмет", negative="no text", asset_id="test-item", canvas=32, role="item")
    assert gate == ["entered", "exited"]
    assert len(paths) == 1
    assert Image.open(paths[0]).format == "PNG"
    url, payload, options = calls[0]
    assert url == "https://chatgpt.com/backend-api/codex/images/generations"
    assert payload == {"model": "gpt-image-2", "prompt": "Literal authored предмет\n\nAvoid: no text", "n": 1, "quality": "medium", "size": "1024x1024", "background": background}
    assert options["headers"]["Authorization"] == "Bearer " + credentials.access_token
    assert options["headers"]["ChatGPT-Account-Id"] == credentials.account_id
    assert "response_format" not in payload


def test_codex_auth_error_is_not_retried_or_replaced_by_procedural(monkeypatch):
    from infini_local.pipelines import visual_sprite_generation as visual
    from infini_local.services.codex_auth import CodexError
    calls, fallbacks = [], []
    def fail(*args, **kwargs):
        calls.append(args)
        raise CodexError("OpenAI HTTP 429: quota reached")
    monkeypatch.setattr(visual, "generate_openai_codex", fail)
    monkeypatch.setattr(visual, "IMAGE_BACKEND", "openai_codex")
    monkeypatch.setattr(visual, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(visual, "SPRITE_RETRIES", 3)
    monkeypatch.setattr(visual, "VISUAL_ALLOW_PROCEDURAL_FALLBACK", True)
    monkeypatch.setattr(visual, "VISUAL_STRICT_AI_AUTHORSHIP", False)
    monkeypatch.setattr(visual, "normalize_asset_prompt", lambda data, role, prompt, canvas, **kwargs: prompt)
    monkeypatch.setattr(visual.visual_asset_pipeline, "generate_procedural_asset", lambda *a, **kw: fallbacks.append(True))
    data = {"id": "test", "visual": {"imagePrompt": "authored sprite"}}
    visual.maybe_generate_sprite(data)
    assert data["visual"]["spriteStatus"] == "failed"
    assert len(calls) == 1
    assert not fallbacks
    result = visual.generate_visual_asset({}, "entity_shot", "authored shot", "", "shot", 32)
    assert result[3] == "failed"
    assert len(calls) == 2
    assert not fallbacks


@pytest.mark.parametrize("mode,marker_role", [
    ("json_object", "system"), ("json_object", None),
    ("json_object", "user"), ("json_object", "developer"),
    ("json_object", "assistant"), ("json_schema", "system"),
    (None, "system"),
])
def test_subscription_json_input_framing_preserves_all_authored_messages(mode, marker_role):
    messages = [{"role": "system", "content": "JSON result." if marker_role == "system" else "Keep authored facts."},
                {"role": "user", "content": "Return Json." if marker_role == "user" else '{"exactFact":14}'}]
    if marker_role in {"developer", "assistant"}:
        messages.append({"role": marker_role, "content": "Json protocol marker."})
    request = {"model": "test-model", "messages": messages, "reasoning": {"effort": "medium"},
               "prompt_cache_key": "exact-authored-key"}
    if mode:
        request["response_format"] = {"type": mode}
        if mode == "json_schema":
            request["response_format"]["json_schema"] = {"name": "test_json", "strict": True, "schema": {"type": "object"}}
    before = copy.deepcopy(request)
    actual = backend._request_payload(request)
    authored = [{"type": "message", "role": message["role"],
                 "content": [{"type": "output_text" if message["role"] == "assistant" else "input_text", "text": message["content"]}]}
                for message in messages if message["role"] != "system"]
    needed = mode == "json_object"
    marker = {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "JSON response."}]}
    assert actual["input"] == ([marker, *authored] if needed else authored)
    assert actual["instructions"] == messages[0]["content"]
    assert actual["model"] == request["model"]
    assert actual["reasoning"] == request["reasoning"]
    assert actual["prompt_cache_key"] == request["prompt_cache_key"]
    assert request == before
    assert backend._request_payload(request) == actual


@pytest.mark.parametrize("cache_key", [None, "infini-static-prefix", "unicode-кэш", "key\r\nextra: value"])
def test_subscription_cache_affinity_reaches_native_session_header(subscription, monkeypatch, cache_key):
    from urllib.parse import quote
    response, credentials = subscription
    sent = []
    monkeypatch.setattr(auth, "post_sse", lambda url, body, **kw: sent.append((url, copy.deepcopy(body), kw)) or copy.deepcopy(response))
    packet = {"model": "test-model", "messages": [{"role": "user", "content": "recipe one"}]}
    if cache_key is not None:
        packet["prompt_cache_key"] = cache_key
    original = copy.deepcopy(packet)
    for content in ("recipe one", "recipe two"):
        packet["messages"][0]["content"] = content
        backend.generate_chat(packet, timeout=3)
    assert len(sent) == 2 and sent[0][1] != sent[1][1]
    for url, body, options in sent:
        assert url == backend.RESPONSES_URL and options["timeout"] == 3
        headers = options["headers"]
        assert headers["Authorization"] == "Bearer " + credentials.access_token
        assert headers["ChatGPT-Account-Id"] == credentials.account_id
        assert headers["originator"] == "infinicrafter"
        assert "thread-id" not in headers  # No fabricated conversation identity.
        if cache_key is None:
            assert "session-id" not in headers and "prompt_cache_key" not in body
        else:
            assert headers["session-id"] == quote(cache_key, safe="")
            assert "\r" not in headers["session-id"] and "\n" not in headers["session-id"]
            assert headers["session-id"].isascii()
            assert body["prompt_cache_key"] == cache_key
    packet["messages"][0]["content"] = original["messages"][0]["content"]
    assert packet == original

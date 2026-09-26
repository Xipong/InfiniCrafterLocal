"""Author cache boundaries and local request-build work, without provider calls."""
from __future__ import annotations

import json

import pytest

from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.pipelines import llm_transport as transport


@pytest.mark.parametrize("mode", ["json_object", "off"])
def test_author_does_not_build_unused_provider_schema(monkeypatch, mode):
    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    calls = []

    def schema():
        calls.append(True)
        return {"type": "object", "properties": {"marker": {"type": "string"}}}

    monkeypatch.setattr(author, "author_item_provider_response_schema", schema)
    request, _, _ = author.build_initial_author_request({}, {}, {}, {}, "one", model_name="test-model")
    assert calls == []
    assert request.get("response_format") == ({"type": "json_object"} if mode == "json_object" else None)


def test_schema_factory_is_evaluated_only_for_schema_mode(monkeypatch):
    schema = {"type": "object", "properties": {"marker": {"type": "string"}}}
    calls = []

    def factory():
        calls.append(True)
        return schema

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    result = transport.llm_json_response_format("probe", schema=factory, strict=True)
    assert calls == [True]
    assert result is not None
    assert result["json_schema"]["schema"] == schema
    assert result["json_schema"]["strict"] is True
    # The result must be actual wire JSON, not a leaked Python callable.
    assert json.loads(json.dumps(result)) == result


def _marked_prefix(request):
    marker = request.get("_infini_prompt_cache")
    assert marker is not None, "production request must declare the reusable instruction/catalog boundary"
    message = request["messages"][marker["messageIndex"]]
    assert message["role"] == "user"
    content = message["content"]
    prefix = content[:marker["prefixChars"]]
    assert prefix.endswith(",")
    return json.loads(prefix[:-1] + "}"), prefix, json.loads(content)


def test_author_declares_exact_recipe_independent_prefix(monkeypatch):
    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    first, first_user, _ = author.build_initial_author_request(
        {"name": "Workbench"}, {"name": "Sword"}, {}, {}, "workbench+sword", model_name="test-model",
    )
    second, second_user, _ = author.build_initial_author_request(
        {"name": "Lens"}, {"name": "Bird"}, {}, {}, "lens+bird", model_name="test-model",
    )
    static, prefix, full = _marked_prefix(first)
    other_static, other_prefix, other_full = _marked_prefix(second)
    assert static == other_static
    assert prefix == other_prefix
    assert len(prefix) > 65000
    assert set(static) == {"priorityHeader", "gameplayAuthoringStages", "runtimeProgramInvariants", "runtimeCapabilityContract", "requiredJsonShape", "diagnosticReport"}
    assert set(full) - set(static) == {"recipeKey", "parents", "balanceCorridor"}
    assert full["recipeKey"] != other_full["recipeKey"]
    assert len(static["runtimeCapabilityContract"]["catalog"]["capabilities"]) == 52
    assert first["messages"][1]["content"] == first_user
    assert second["messages"][1]["content"] == second_user


class _RequestCaptured(BaseException):
    """Stop at the real transport seam without a remote request or fake response."""


@pytest.mark.parametrize("syntax_only", [False, True])
def test_repair_declares_only_static_guidance_as_cacheable(monkeypatch, syntax_only):
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    from infini_local.core.runtime_authoring import validate_runtime_program

    monkeypatch.setattr(author, "USE_LLM", True)
    monkeypatch.setattr(author, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    requests = []

    def capture(request, **_kwargs):
        requests.append(request)
        raise _RequestCaptured()

    monkeypatch.setattr(author, "llm_chat_json", capture)
    for label in ("first", "second"):
        with pytest.raises(_RequestCaptured):
            if syntax_only:
                author._repair_malformed_author_json(
                    malformed_raw_text='{"name": "' + label,
                    parse_error=ValueError(label),
                    original_recipe_context=json.dumps({"recipeKey": label}),
                    model_name="test-model",
                )
            else:
                item = build_runtime_fixture("workbench_blade")
                item["name"] = label
                use = next(c for c in item["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")
                del use["params"]["useStyle"]
                report = validate_runtime_program(item)
                author.repair_author_item_after_failure(item, {"name": label}, {}, {}, {}, label, failure_report=report)
    static, prefix, full = _marked_prefix(requests[0])
    other_static, other_prefix, other_full = _marked_prefix(requests[1])
    assert static == other_static
    assert prefix == other_prefix
    assert full != other_full
    if syntax_only:
        assert set(static) == {"schema", "task", "rules", "allowedCallParamsReadOnly", "requiredJsonShape"}
    else:
        assert set(static) == {"schema", "task", "rules", "runtimeVersions", "runtimeExecutionTruth"}
        # Conditional cards remain scoped, never replaced by the entire Author catalog for a cache hit.
        assert "blockerCapabilities" not in static
        assert "repairScope" not in static
        assert list(full)[-1] == "requiredJsonShape"


@pytest.mark.parametrize("repair", [False, True])
def test_vfx_cache_boundary_survives_production_transport_helper(monkeypatch, repair):
    from infini_local.core import vfx_manifest as vfx
    from infini_local.core.runtime_authoring import compile_runtime_program
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

    monkeypatch.setattr(author, "USE_LLM", True)
    monkeypatch.setattr(author, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    requests = []

    def capture(request, **_kwargs):
        requests.append(request)
        raise _RequestCaptured()

    monkeypatch.setattr(author, "llm_chat_json", capture)
    for name in ("workbench_blade", "throwing_axe"):
        data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
        data["name"] = name
        packet = vfx._prompt_packet(data, {"name": name}, {})
        with pytest.raises(_RequestCaptured):
            vfx._request(author.call_llm_vfx_director, packet,
                         repair_errors=[] if repair else None, previous={}, repair_scope={})
    static, prefix, full = _marked_prefix(requests[0])
    other_static, other_prefix, other_full = _marked_prefix(requests[1])
    assert prefix == other_prefix and static == other_static
    assert full != other_full
    assert set(static) == ({"task", "rules"} if repair else {"schema", "rules"})
    assert "outputSchema" not in static

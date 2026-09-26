"""Cache boundaries are byte prefixes of complete, unchanged stage JSON messages."""
from __future__ import annotations

import copy
import json

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.core.runtime_authoring import compile_runtime_program


def _craft(kind: str) -> dict:
    data = compile_runtime_program(build_runtime_fixture(kind))
    data["name"] = f"different name: {kind}"
    data["realization"] = {"description": f"literal {kind} description", "playerExperience": kind}
    data["visualKit"] = {"schema": visual.VISUAL_KIT_SCHEMA, "animationPlan": f"{kind} motion"}
    return data


def _static_json_prefix(payload: dict, keys: tuple[str, ...]) -> str:
    full = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    static = json.dumps({key: payload[key] for key in keys}, ensure_ascii=False, separators=(",", ":"))[:-1] + ","
    assert full.startswith(static)
    return static


@pytest.mark.parametrize("repair", [False, True])
def test_visual_request_keeps_complete_json_and_marks_constant_static_prefix(monkeypatch, repair: bool) -> None:
    marked = []
    sent = []
    actual_mark = visual.with_prompt_cache_prefix

    def mark(request, *, message_index, prefix_chars):
        marked.append((request, message_index, prefix_chars))
        return actual_mark(request, message_index=message_index, prefix_chars=prefix_chars)

    def send(request, **kwargs):
        sent.append(request)
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(visual, "with_prompt_cache_prefix", mark, raising=False)
    monkeypatch.setattr(visual, "llm_chat_json", send)
    payloads = []
    for kind in ("workbench_blade", "door_on_chain"):
        data = _craft(kind)
        kwargs = {}
        if repair:
            previous = visual.MalformedVisualDirectorOutput(raw_text="{broken", error="missing brace")
            kwargs = {"repair_errors": [{"path": "$", "message": "malformed_json"}],
                      "previous": previous,
                      "repair_scope": {"fieldPermissions": {"itemPaths": [""]}}}
        visual._request_visual_kit(data, {"name": "A"}, {"name": "B"}, {}, {}, **kwargs)
        payloads.append(json.loads(sent[-1]["messages"][1]["content"]))
    keys = ("task", "assetModeCatalog", "rules")
    prefixes = [_static_json_prefix(p, keys) for p in payloads]
    assert prefixes[0] == prefixes[1]
    assert len(prefixes[0]) > 100
    assert len(marked) == len(sent) == 2
    for request, index, count in marked:
        assert index == 1
        assert any(request["messages"] == sent_request["messages"] for sent_request in sent)
        assert count == len(prefixes[0])
        assert len(request["messages"]) == 2
    assert all(request["_infini_prompt_cache"] == {"messageIndex": 1, "prefixChars": len(prefixes[0])} for request in sent)
    assert payloads[0]["assetModeCatalog"] == visual.visual_asset_mode_catalog()
    assert payloads[0]["rules"] == payloads[1]["rules"]
    assert payloads[0]["responseSchema"] != payloads[1]["responseSchema"]
    if repair:
        for payload in payloads:
            assert payload["exactErrors"] == kwargs["repair_errors"]
            assert payload["malformedRawText"] == "{broken"
            assert payload["repairScope"] == kwargs["repair_scope"]
            assert set(payload) == {"task", "assetModeCatalog", "rules", "exactErrors", "malformedRawText", "repairScope", "brokenFragments", "validGeneratedContext", "parentFactsReadOnly", "runtimeEntitiesReadOnly", "itemReadOnly", "equipmentOverlayReadOnly", "responseSchema"}
    else:
        for payload, kind in zip(payloads, ("workbench_blade", "door_on_chain")):
            assert payload["item"]["name"] == f"different name: {kind}"
            assert payload["item"]["realization"]["description"] == f"literal {kind} description"
            assert payload["requiredEntityIds"] == [r["id"] for r in _craft(kind)["runtimeProgram"]["entities"]]
            assert set(payload) == {"task", "assetModeCatalog", "rules", "item", "parents", "runtimeEntities", "requiredEntityIds", "equipmentOverlayReadOnly", "responseSchema"}
    assert sent[0]["messages"][1]["content"][len(prefixes[0]):] != sent[1]["messages"][1]["content"][len(prefixes[0]):]


def test_visual_catalog_change_invalidates_prefix(monkeypatch) -> None:
    sent = []
    monkeypatch.setattr(visual, "with_prompt_cache_prefix", lambda request, **kwargs: request, raising=False)
    monkeypatch.setattr(visual, "llm_chat_json", lambda request, **kwargs: sent.append(request) or {"choices": [{"message": {"content": "{}"}}]})
    data = _craft("workbench_blade")
    visual._request_visual_kit(data, {}, {}, {}, {})
    before = json.loads(sent[-1]["messages"][1]["content"])
    catalog = copy.deepcopy(visual.visual_asset_mode_catalog())
    monkeypatch.setattr(visual, "visual_asset_mode_catalog", lambda: [*catalog, {"mode": "changed", "description": "catalog revision"}])
    visual._request_visual_kit(data, {}, {}, {}, {})
    after = json.loads(sent[-1]["messages"][1]["content"])
    assert _static_json_prefix(before, ("task", "assetModeCatalog", "rules")) != _static_json_prefix(after, ("task", "assetModeCatalog", "rules"))
    assert {k: v for k, v in before.items() if k != "assetModeCatalog"} == {k: v for k, v in after.items() if k != "assetModeCatalog"}


def test_visual_structured_repair_keeps_errors_and_frozen_context_after_prefix(monkeypatch) -> None:
    sent = []
    monkeypatch.setattr(visual, "llm_chat_json", lambda request, **kwargs: sent.append(request) or {"choices": [{"message": {"content": "{}"}}]})
    previous = {"schema": visual.VISUAL_KIT_SCHEMA, "item": {"prompt": "valid literal item"}, "entities": []}
    errors = [{"path": "$.item.silhouette", "message": "required"}]
    scope = {"itemMutable": True, "fieldPermissions": {"itemPaths": ["silhouette"]}}
    visual._request_visual_kit(_craft("workbench_blade"), {}, {}, {}, {},
                               repair_errors=errors, previous=previous, repair_scope=scope)
    payload = json.loads(sent[0]["messages"][1]["content"])
    assert payload["exactErrors"] == errors
    assert payload["repairScope"] == scope
    assert payload["brokenFragments"]["item"] == previous["item"]
    assert payload["malformedRawText"] == ""
    assert sent[0]["_infini_prompt_cache"]["prefixChars"] == len(_static_json_prefix(payload, ("task", "assetModeCatalog", "rules")))


@pytest.mark.parametrize("repair", [False, True])
def test_vfx_packet_static_keys_precede_runtime_specific_content(repair: bool) -> None:
    payloads = []
    for kind in ("workbench_blade", "door_on_chain"):
        data = _craft(kind)
        packet = vfx._prompt_packet(data, {"name": f"parent {kind}"}, {"name": "B"})
        if repair:
            captured = []
            previous = vfx.MalformedVfxDirectorOutput(raw_text="{unclosed", error="invalid")
            vfx._request(lambda system, user, *args, **kwargs: captured.append((user, kwargs["messages"])) or {}, packet,
                         repair_errors=[{"path": "$", "message": "malformed_json"}], previous=previous,
                         repair_scope={"fieldPermissions": {"slots": []}})
            payload, messages = captured[0]
            assert json.loads(messages[1]["content"]) == payload
            assert payload["malformedRawText"] == "{unclosed"
            assert payload["repairScope"] == {"fieldPermissions": {"slots": []}}
            assert payload["exactErrors"] == [{"path": "$", "message": "malformed_json"}]
            assert payload["outputSchema"] == vfx._vfx_repair_schema_from_packet(packet)
            assert set(payload) == {"task", "rules", "item", "acceptedVisualKitReadOnly", "runtimeSurfaceReadOnly", "exactErrors", "repairScope", "brokenFragments", "malformedRawText", "validGeneratedContext", "outputSchema"}
            keys = vfx.VFX_REPAIR_PROMPT_STATIC_KEYS
        else:
            payload = packet
            keys = vfx.VFX_PROMPT_STATIC_KEYS
            assert set(payload) == {"schema", "rules", "item", "parents", "acceptedVisualKit", "runtimeSurface", "outputSchema"}
            assert payload["parents"][0]["name"] == f"parent {kind}"
            assert payload["acceptedVisualKit"] == data["visualKit"]
            assert payload["runtimeSurface"] == vfx.vfx_director_surface(data)
            assert payload["outputSchema"] == vfx.vfx_director_schema(data)
            assert list(payload["runtimeSurface"])[-2:] == ["runtimePairs", "runtimeVisualRoles"]
        assert list(payload)[:len(keys)] == list(keys)
        payloads.append(payload)
    prefixes = [_static_json_prefix(p, keys) for p in payloads]
    assert prefixes[0] == prefixes[1]
    assert len(prefixes[0]) > 100
    assert payloads[0]["outputSchema"] != payloads[1]["outputSchema"]
    assert "workbench_blade" not in prefixes[0] and "door_on_chain" not in prefixes[0]


def test_vfx_structured_repair_preserves_frozen_context_after_prefix() -> None:
    packet = vfx._prompt_packet(_craft("workbench_blade"), {}, {})
    previous = {"schema": vfx.VFX_DIRECTOR_SCHEMA, "effectMagnitude": 0.5, "slots": []}
    errors = [{"path": "$.effectMagnitude", "message": "invalid number"}]
    scope = {"mutableGlobals": ["effectMagnitude"], "fieldPermissions": {"globals": {"effectMagnitude": [""]}}}
    captured = []
    vfx._request(lambda system, user, *args, **kwargs: captured.append((user, kwargs["messages"])) or {}, packet,
                 repair_errors=errors, previous=previous, repair_scope=scope)
    payload, messages = captured[0]
    assert json.loads(messages[1]["content"]) == payload
    assert payload["exactErrors"] == errors
    assert payload["repairScope"] == scope
    assert payload["brokenFragments"]["globals"] == {"effectMagnitude": 0.5}
    assert payload["malformedRawText"] == ""
    assert messages[1]["content"].startswith(_static_json_prefix(payload, vfx.VFX_REPAIR_PROMPT_STATIC_KEYS))

"""Actual serialized director/Repair packets, numeric units and cache boundaries."""
from __future__ import annotations
import copy
import json
import pytest
from infini_local.core import vfx_manifest as vfx
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_low_level_three_stage_pipeline import wire_transport


def _craft(kind):
    data = compile_runtime_program(build_runtime_fixture(kind))
    data["name"] = f"different name: {kind}"
    data["realization"] = {"description": f"literal {kind} description", "playerExperience": kind}
    data["visualKit"] = {"schema": visual.VISUAL_KIT_SCHEMA, "animationPlan": f"{kind} motion"}
    return data


def _static_json_prefix(payload, keys):
    full = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    prefix = json.dumps({key: payload[key] for key in keys}, ensure_ascii=False, separators=(",", ":"))[:-1] + ","
    assert full.startswith(prefix)
    return prefix


@pytest.mark.parametrize("stage", ["visual", "vfx"])
@pytest.mark.parametrize("kind", ["director", "malformed-repair", "scoped-repair"])
def test_stage_packet_cache_boundary_and_frozen_context(wire_transport, stage, kind):
    responses, sent = wire_transport
    payloads = []
    for fixture in ("workbench_blade", "door_on_chain"):
        data = _craft(fixture)
        errors: list[dict] = []
        scope: dict = {}
        malformed = kind == "malformed-repair"
        repair = kind != "director"
        if stage == "visual":
            previous = visual.MalformedVisualDirectorOutput("{broken", "missing brace") if malformed else {"schema": visual.VISUAL_KIT_SCHEMA, "item": {"prompt": "valid literal item"}, "entities": []}
            errors = [{"path": "$" if malformed else "$.item.silhouette", "message": "malformed_json" if malformed else "required"}]
            scope = {"itemMutable": True, "fieldPermissions": {"itemPaths": ["" if malformed else "silhouette"]}}
            responses.append({})
            visual._request_visual_kit(data, {"name": "A"}, {"name": "B"}, {}, {},
                **({"repair_errors": errors, "previous": previous, "repair_scope": scope} if repair else {}))
            request = sent[-1]
            payload = json.loads(request["messages"][1]["content"])
            keys = ("task", "assetModeCatalog", "rules")
            assert len(request["messages"]) == 2
            assert request["_infini_prompt_cache"] == {"messageIndex": 1, "prefixChars": len(_static_json_prefix(payload, keys))}
            assert payload["assetModeCatalog"] == visual.visual_asset_mode_catalog()
            if repair:
                assert set(payload) == {"task", "assetModeCatalog", "rules", "exactErrors", "malformedRawText", "repairScope", "brokenFragments", "validGeneratedContext", "parentFactsReadOnly", "runtimeEntitiesReadOnly", "itemReadOnly", "equipmentOverlayReadOnly", "responseSchema"}
                if not malformed:
                    assert isinstance(previous, dict)
                    assert payload["brokenFragments"]["item"] == previous["item"]
            else:
                assert set(payload) == {"task", "assetModeCatalog", "rules", "item", "parents", "runtimeEntities", "requiredEntityIds", "equipmentOverlayReadOnly", "responseSchema"}
                assert payload["item"]["name"] == f"different name: {fixture}"
                assert payload["item"]["realization"]["description"] == f"literal {fixture} description"
                assert payload["requiredEntityIds"] == [r["id"] for r in data["runtimeProgram"]["entities"]]
            schema_key = "responseSchema"
        else:
            packet = vfx._prompt_packet(data, {"name": f"parent {fixture}"}, {"name": "B"})
            if repair:
                captured = []
                previous = vfx.MalformedVfxDirectorOutput("{broken", "invalid") if malformed else {"schema": vfx.VFX_DIRECTOR_SCHEMA, "effectMagnitude": 0.5, "slots": []}
                errors = [{"path": "$" if malformed else "$.effectMagnitude", "message": "malformed_json" if malformed else "invalid number"}]
                scope = {"mutableGlobals": ["effectMagnitude"], "fieldPermissions": {"globals": {"effectMagnitude": [""]}}}
                vfx._request(lambda _system, user, *args, **kwargs: captured.append((user, kwargs["messages"])) or {}, packet,
                    repair_errors=errors, previous=previous, repair_scope=scope)
                payload, messages = captured[0]
                assert json.loads(messages[1]["content"]) == payload
                assert payload["outputSchema"] == vfx._vfx_repair_schema_from_packet(packet)
                assert set(payload) == {"task", "rules", "item", "acceptedVisualKitReadOnly", "acceptedRuntimeProgramReadOnly", "runtimeSurfaceReadOnly", "exactErrors", "repairScope", "brokenFragments", "malformedRawText", "validGeneratedContext", "outputSchema"}
                keys = vfx.VFX_REPAIR_PROMPT_STATIC_KEYS
                if not malformed:
                    assert payload["brokenFragments"]["globals"] == {"effectMagnitude": 0.5}
                assert messages[1]["content"].startswith(_static_json_prefix(payload, keys))
            else:
                payload = packet
                keys = vfx.VFX_PROMPT_STATIC_KEYS
                assert set(payload) == {"schema", "rules", "item", "parents", "acceptedVisualKit", "acceptedRuntimeProgramReadOnly", "runtimeSurface", "outputSchema"}
                assert payload["parents"][0]["name"] == f"parent {fixture}"
                assert payload["acceptedVisualKit"] == data["visualKit"]
                assert payload["runtimeSurface"] == vfx.vfx_director_surface(data)
                assert payload["outputSchema"] == vfx.vfx_director_schema(data)
                assert list(payload["runtimeSurface"])[-2:] == ["runtimePairs", "runtimeVisualRoles"]
            schema_key = "outputSchema"
        if repair:
            assert payload["exactErrors"] == errors
            assert payload["repairScope"] == scope
            assert payload["malformedRawText"] == ("{broken" if malformed else "")
        assert list(payload)[:len(keys)] == list(keys)
        payloads.append(payload)
    before, after = payloads
    prefixes = [_static_json_prefix(p, keys) for p in payloads]
    assert prefixes[0] == prefixes[1] and len(prefixes[0]) > 100
    assert before[schema_key] != after[schema_key]
    assert before["rules"] == after["rules"]
    assert "workbench_blade" not in prefixes[0] and "door_on_chain" not in prefixes[0]
    if stage == "visual":
        assert len(sent) == 2
        assert sent[0]["messages"][1]["content"][len(prefixes[0]):] != sent[1]["messages"][1]["content"][len(prefixes[0]):]


def test_catalog_revision_changes_only_static_prefix(wire_transport, monkeypatch):
    responses, sent = wire_transport
    data = _craft("workbench_blade")
    responses.extend([{}, {}])
    visual._request_visual_kit(data, {}, {}, {}, {})
    before = json.loads(sent[-1]["messages"][1]["content"])
    catalog = copy.deepcopy(visual.visual_asset_mode_catalog())
    monkeypatch.setattr(visual, "visual_asset_mode_catalog", lambda: [*catalog, {"mode": "changed", "description": "catalog revision"}])
    visual._request_visual_kit(data, {}, {}, {}, {})
    after = json.loads(sent[-1]["messages"][1]["content"])
    keys = ("task", "assetModeCatalog", "rules")
    assert _static_json_prefix(before, keys) != _static_json_prefix(after, keys)
    assert {k: v for k, v in before.items() if k != "assetModeCatalog"} == {k: v for k, v in after.items() if k != "assetModeCatalog"}


@pytest.mark.parametrize("kind", ["director", "scoped-repair", "malformed-repair"])
def test_visual_schema_and_numeric_rules_reach_real_transport(wire_transport, monkeypatch, kind):
    responses, sent = wire_transport
    monkeypatch.setattr(visual, "equipment_overlay_requirement", lambda _: {"required": True, "slot": "head"})
    # Keep the real common-options/stage/cache pipeline; transport owns the wire.
    parent = {"name": "Sword Named Parent", "internalName": "SwordNamedParent", "sourceMod": "Terraria", "damage": 20, "tags": ["sword", "weapon"]}
    canonical = {"class": "weapon", "hardTags": ["sword"], "headNoun": "sword"}
    data = _craft("workbench_blade")
    malformed = kind == "malformed-repair"
    kwargs = {} if kind == "director" else {
        "repair_errors": [{"path": "$" if malformed else "$.item.inventoryScale", "message": "malformed_json" if malformed else "invalid"}],
        "previous": visual.MalformedVisualDirectorOutput("{broken", "bad json") if malformed else {"schema": visual.VISUAL_KIT_SCHEMA, "item": {"inventoryScale": "invalid"}, "entities": []},
        "repair_scope": {"itemMutable": True, "fieldPermissions": {"itemPaths": ["" if malformed else "inventoryScale"]}},
    }
    responses.append({})
    assert visual._request_visual_kit(data, parent, parent, canonical, canonical, **kwargs) == {}
    request = sent[0]
    payload = json.loads(request["messages"][1]["content"])
    schema = payload["responseSchema"]
    assert request["response_format"]["type"] == "json_schema"
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["response_format"]["json_schema"]["schema"] == schema
    assert request["temperature"] == (0.5 if kind == "director" else 0.12)
    if kind == "director":
        assert "double-quoted JSON object keys" in request["messages"][0]["content"]
    rules = "\n".join(payload["rules"])
    for surface in (request["messages"][0]["content"], rules):
        for phrase in ("same physical object", "reuse_item_icon", "visualProjectRef=item", "regardless of its entityId", "kind=item_body must use baked_sprite", "another non-item_body entity"):
            assert phrase in surface
    assert any("transparent background" in rule and "opaque background" in rule for rule in payload["rules"])
    assert payload["assetModeCatalog"] == [
        {"mode": "baked_sprite", "runtimeEffect": "Generate and deliver a distinct PNG for this exact runtime entity."},
        {"mode": "no_asset", "runtimeEffect": "Deliver no PNG and draw no entity body; independent runtime VFX may still draw."},
        {"mode": "reuse_item_icon", "runtimeEffect": "Deliver no separate PNG; resolve this entity to the item_body generated PNG with identical pixels."},
        {"mode": "runtime_geometry", "runtimeEffect": "Deliver no PNG; draw the built-in bounded runtime primitive from entity hitbox and light fields."},
    ]
    props = schema["properties"]
    if kind == "director":
        assert props["entities"]["minItems"] == len(data["runtimeProgram"]["entities"])
        item, overlay = props["item"]["properties"], props["equipOverlay"]["properties"]
    else:
        item, overlay = props["itemPatch"]["anyOf"][0]["properties"], props["equipOverlayPatch"]["anyOf"][0]["properties"]
        encoded = json.dumps(payload["parentFactsReadOnly"]).casefold()
        assert all(token not in encoded for token in ("canonical", "hardtags", "headnoun", '"tags"'))
        assert payload["parentFactsReadOnly"]["parentA"] == {"packet": visual.raw_parent_card_for_llm(parent)}
        deletion = props["entityIndicesDelete"]
        assert deletion["items"]["type"] == "integer" and deletion["items"]["minimum"] == 0
        description = (deletion.get("description", "") + " " + deletion["items"].get("description", "")).lower()
        assert all(token in description for token in ("zero-based", "index", "entities"))
    item = {key: value["anyOf"][0] if value.get("anyOf", [None])[-1] == {"type": "null"} else value for key, value in item.items()}
    assert item["preferredCanvasSize"]["enum"] == [24, 32, 48, 64, 96, 128]
    assert overlay["preferredCanvasSize"]["enum"] == [32, 48, 64, 96]
    for canvas in (item["preferredCanvasSize"], overlay["preferredCanvasSize"]):
        description = canvas["description"].lower()
        assert all(token in description for token in ("square", "canvas", "pixels"))
        assert "world size" in description or "display size" in description
    for name, label in (("inventoryScale", "inventory"), ("worldScale", "world")):
        field = item[name]
        assert field["minimum"] == 0.25 and field["maximum"] == 4.0
        assert all(token in field["description"].lower() for token in (label, "factor", "1"))
    assert "fit" in item["inventoryScale"]["description"].lower()
    assert "dropped" in item["worldScale"]["description"].lower()
    branches = (props["entities"] if kind == "director" else props["entitiesUpsert"])["items"]["oneOf"]
    assert {b["properties"]["assetMode"]["const"] for b in branches} == {"baked_sprite", "reuse_item_icon", "runtime_geometry", "no_asset"}
    descriptions = {b["properties"]["scale"]["description"] for b in branches}
    assert len(descriptions) == 1
    assert all(b["properties"]["scale"]["minimum"] == 0.25 and b["properties"]["scale"]["maximum"] == 4.0 for b in branches)
    assert all(token in next(iter(descriptions)).lower() for token in ("visual", "factor", "1", "hitbox", "drawscale", "worldscale"))

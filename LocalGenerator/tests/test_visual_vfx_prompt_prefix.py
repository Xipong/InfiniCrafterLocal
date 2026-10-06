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


def test_default_author_system_explicitly_targets_terraria(monkeypatch):
    from infini_local.core import llm_config
    from infini_local.pipelines import llm_authoring_pipeline as author

    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Default", raising=False)
    request, user, system = author.build_initial_author_request({}, {}, {}, {}, "target-game", model_name="test-model")
    assert "Target game: Terraria (tModLoader)" in system
    assert request["messages"][0]["content"] == system
    assert request["messages"][1]["content"] == user
    assert "Terraria Like art direction" not in system


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_prompt_style_reaches_all_real_stage_requests_without_changing_contracts(wire_transport, monkeypatch, format_mode):
    from infini_local.core import llm_config
    from infini_local.pipelines import llm_authoring_pipeline as author, llm_transport
    from test_low_level_three_stage_pipeline import _accepted_visual_data

    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    responses, sent = wire_transport
    source = build_runtime_fixture("fishing_platform_tool")
    frozen = copy.deepcopy(source)
    snapshots = []
    for style in ("Default", "Terraria Like"):
        monkeypatch.setattr(llm_config, "PROMPT_STYLE", style, raising=False)
        sent.clear()
        request, user, _ = author.build_initial_author_request({}, {}, {}, {}, "style-proof", model_name="test-model")
        sent.append(request)
        raw = json.dumps(source)
        responses.append(raw)
        prepared, _ = author._repair_malformed_author_json(
            malformed_raw_text=raw[:-1] + ",}", parse_error=ValueError("trailing comma"),
            original_recipe_context=user, model_name="test-model",
        )
        assert prepared == frozen
        broken = copy.deepcopy(source)
        stats = next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
        stats["params"]["damage"] = -1
        replacement = copy.deepcopy(stats)
        original_stats = next(row for row in source["runtimeProgram"]["calls"] if row["id"] == stats["id"])
        replacement["params"]["damage"] = original_stats["params"]["damage"]
        responses.append({"note": "exact damage repair", "realizationReplacement": copy.deepcopy(source["realization"]), "callsUpsert": [replacement]})
        repaired = author.repair_author_item_after_failure(
            broken, {}, {}, {}, {}, "style-proof", failure_report=author.validate_runtime_program(broken),
        )
        assert repaired["runtimeProgram"] == frozen["runtimeProgram"]
        data = _accepted_visual_data("workbench_blade")
        data_before = copy.deepcopy(data)
        for repair in (False, True):
            responses.append({})
            visual._request_visual_kit(data, {}, {}, {}, {}, **({
                "repair_errors": [{"path": "$.item.silhouette", "message": "required"}],
                "previous": {"schema": visual.VISUAL_KIT_SCHEMA, "item": {"prompt": "literal frozen item"}, "entities": []},
                "repair_scope": {"itemMutable": True, "fieldPermissions": {"itemPaths": ["silhouette"]}},
            } if repair else {}))
            responses.append({})
            vfx._request(author.call_llm_vfx_director, vfx._prompt_packet(data, None, None), **({
                "repair_errors": [{"path": "$.effectMagnitude", "message": "invalid"}],
                "previous": {"schema": vfx.VFX_DIRECTOR_SCHEMA, "effectMagnitude": 2.0, "slots": []},
                "repair_scope": {"mutableGlobals": ["effectMagnitude"], "fieldPermissions": {"globals": {"effectMagnitude": [""]}}},
            } if repair else {}))
        assert data == data_before and source == frozen
        assert len(sent) == 7
        for request in sent:
            system = request["messages"][0]["content"]
            assert "Target game: Terraria (tModLoader)" in system
            assert ("Terraria Like art direction" in system) == (style == "Terraria Like")
            assert "frozen fields during Repair" in system
            if style == "Terraria Like":
                for phrase in ("compact coherent palette", "discrete shadow/highlight bands", "1x gameplay size", "soft-alpha"):
                    assert phrase in system
        snapshots.append(copy.deepcopy(sent))
    for before, after in zip(*snapshots):
        # The only setting-dependent bytes are advisory system instructions.
        before["messages"][0]["content"] = after["messages"][0]["content"]
        assert before == after


def test_invalid_prompt_style_is_not_silently_defaulted(monkeypatch):
    from infini_local.core import llm_config
    from infini_local.pipelines import llm_authoring_pipeline as author

    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Unknown", raising=False)
    with pytest.raises(ValueError, match="INFINI_PROMPT_STYLE"):
        author.build_initial_author_request({}, {}, {}, {}, "invalid-style", model_name="test-model")


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
                assert set(payload) == {"task", "assetModeCatalog", "rules", "exactErrors", "malformedRawText", "repairScope", "brokenFragments", "validGeneratedContext", "parentFactsReadOnly", "runtimeEntitiesReadOnly", "itemReadOnly", "equipmentOverlayReadOnly", "acceptedPresentationMechanicsReadOnly", "spritePresentationReadOnly", "responseSchema"}
                if not malformed:
                    assert isinstance(previous, dict)
                    assert payload["brokenFragments"]["item"] == previous["item"]
            else:
                assert set(payload) == {"task", "assetModeCatalog", "rules", "item", "parents", "runtimeEntities", "requiredEntityIds", "equipmentOverlayReadOnly", "acceptedPresentationMechanicsReadOnly", "spritePresentationReadOnly", "responseSchema"}
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
                assert set(payload) == {"task", "rules", "runtimeVocabularyReadOnly", "item", "acceptedVisualKitReadOnly", "acceptedRuntimeProgramReadOnly", "runtimeSurfaceReadOnly", "exactErrors", "repairScope", "brokenFragments", "malformedRawText", "validGeneratedContext", "outputSchema"}
                keys = vfx.VFX_REPAIR_PROMPT_STATIC_KEYS
                if not malformed:
                    assert payload["brokenFragments"]["globals"] == {"effectMagnitude": 0.5}
                assert messages[1]["content"].startswith(_static_json_prefix(payload, keys))
            else:
                payload = packet
                keys = vfx.VFX_PROMPT_STATIC_KEYS
                assert set(payload) == {"schema", "rules", "runtimeVocabulary", "item", "parents", "acceptedVisualKit", "acceptedRuntimeProgramReadOnly", "runtimeSurface", "outputSchema"}
                assert payload["parents"][0]["name"] == f"parent {fixture}"
                assert payload["acceptedVisualKit"] == data["visualKit"]
                assert {**payload["runtimeVocabulary"], **payload["runtimeSurface"]} == vfx.vfx_director_surface(data)
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


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("kind", ["director", "scoped-repair", "malformed-repair"])
def test_vfx_invariant_vocabulary_enlarges_actual_wire_prefix(wire_transport, monkeypatch, format_mode, kind):
    from infini_local.pipelines import llm_authoring_pipeline as stage, llm_transport
    from test_low_level_three_stage_pipeline import _accepted_visual_data, _vfx_output
    responses, sent = wire_transport
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    prefixes, payloads, tails = [], [], []
    dynamic_fields = {"texturedPathSources", "entityTextureSources", "runtimePairs", "runtimeVisualRoles"}
    repair = kind != "director"
    for fixture in ("workbench_blade", "door_on_chain", "returning_potion"):
        data = _accepted_visual_data(fixture)
        data["id"], data["name"] = fixture, f"different name: {fixture}"
        data["realization"]["description"] = f"literal {fixture} description"
        data["realization"]["playerExperience"] = fixture
        parent_a = {"name": f"parent {fixture}", "internalName": fixture,
                    "generatedParentSummary": {"description": f"literal parent {fixture}"}}
        parent_b = {"name": f"other parent {fixture}"}
        color = "cyan" if fixture == "workbench_blade" else "orange"
        data["visualKit"]["item"]["effectColor"] = color
        data["visual"]["effectColor"] = color
        frozen = copy.deepcopy((data, parent_a, parent_b))
        packet = vfx._prompt_packet(data, parent_a, parent_b)
        kwargs = {}
        previous, errors, scope, context, frozen_repair = None, [], {}, {}, None
        if repair:
            previous = vfx.MalformedVfxDirectorOutput("{broken " + fixture, "invalid") if kind == "malformed-repair" else _vfx_output(data)
            errors = [{"path": "$" if kind == "malformed-repair" else "$.slots[0].alpha", "message": "invalid " + fixture}]
            scope = vfx._build_vfx_repair_scope(previous, errors)
            context = vfx._vfx_repair_context(previous, scope)
            kwargs = {"repair_errors": errors, "previous": previous, "repair_scope": scope}
            frozen_repair = copy.deepcopy((previous, errors, scope))
        responses.append({})
        vfx._request(stage.call_llm_vfx_director, packet, **kwargs)
        request = sent[-1]
        payload = json.loads(request["messages"][1]["content"])
        keys = vfx.VFX_REPAIR_PROMPT_STATIC_KEYS if repair else vfx.VFX_PROMPT_STATIC_KEYS
        prefix = _static_json_prefix(payload, keys)
        vocabulary_key = "runtimeVocabularyReadOnly" if repair else "runtimeVocabulary"
        surface_key = "runtimeSurfaceReadOnly" if repair else "runtimeSurface"
        assert vocabulary_key in keys, "canonical invariant VFX vocabulary must precede recipe facts"
        vocabulary, surface = payload[vocabulary_key], payload[surface_key]
        canonical = vfx.vfx_director_surface(data)
        assert set(surface) == dynamic_fields
        assert not (set(vocabulary) & set(surface))
        assert json.dumps({**vocabulary, **surface}, sort_keys=True) == json.dumps(canonical, sort_keys=True)
        assert len(prefix) > 7000
        assert request["_infini_prompt_cache"] == {"messageIndex": 1, "prefixChars": len(prefix)}
        assert list(payload)[len(keys)] == "item"
        assert request["response_format"]["type"] == format_mode
        if format_mode == "json_schema":
            assert request["response_format"]["json_schema"]["schema"] == payload["outputSchema"]
            assert request["response_format"]["json_schema"]["strict"] is True
        assert payload["item"] == packet["item"]
        assert payload["acceptedVisualKitReadOnly" if repair else "acceptedVisualKit"] == data["visualKit"]
        assert payload["acceptedRuntimeProgramReadOnly"] == packet["acceptedRuntimeProgramReadOnly"]
        if repair:
            assert payload["exactErrors"] == errors[:24]
            assert payload["repairScope"] == scope
            assert payload["brokenFragments"] == context["broken"]
            assert payload["validGeneratedContext"] == context["validReadOnly"]
            assert payload["malformedRawText"] == context["malformedRawText"]
            assert (previous, errors, scope) == frozen_repair
            assert payload["outputSchema"] == vfx.vfx_repair_schema(data)
        else:
            assert payload["parents"] == packet["parents"]
            assert payload["outputSchema"] == vfx.vfx_director_schema(data)
        assert (data, parent_a, parent_b) == frozen
        prefixes.append(prefix)
        payloads.append(payload)
        tails.append(request["messages"][1]["content"][len(prefix):])
    assert len(set(prefixes)) == 1
    assert len(set(tails)) == len(payloads)
    # Stable prefixes must not hide accepted-recipe changes in a frozen tail.
    before, after = payloads[:2]
    for field in dynamic_fields:
        assert before[surface_key][field] != after[surface_key][field], field
    for field in ("item", "acceptedRuntimeProgramReadOnly", "outputSchema",
                  "acceptedVisualKitReadOnly" if repair else "acceptedVisualKit"):
        assert before[field] != after[field], field
    if repair:
        assert before["exactErrors"] != after["exactErrors"]
        if kind == "malformed-repair":
            assert before["malformedRawText"] != after["malformedRawText"]
        else:
            assert before["brokenFragments"] != after["brokenFragments"]
    else:
        assert before["parents"] != after["parents"]


@pytest.mark.parametrize("repair", [False, True])
def test_vfx_canonical_vocabulary_revision_reaches_actual_prefix_only(wire_transport, monkeypatch, repair):
    from infini_local.pipelines import llm_authoring_pipeline as stage
    responses, sent = wire_transport
    data = _craft("workbench_blade")
    frozen = copy.deepcopy(data)
    packets = []
    kwargs = {"repair_errors": [], "previous": {}, "repair_scope": {}} if repair else {}
    keys = vfx.VFX_REPAIR_PROMPT_STATIC_KEYS if repair else vfx.VFX_PROMPT_STATIC_KEYS
    vocabulary_key = "runtimeVocabularyReadOnly" if repair else "runtimeVocabulary"
    surface_key = "runtimeSurfaceReadOnly" if repair else "runtimeSurface"
    original_semantics = vfx._RENDERER_SEMANTICS["impactSprite"]
    for revised in (False, True):
        if revised:
            monkeypatch.setitem(vfx._RENDERER_SEMANTICS, "impactSprite", original_semantics + " Canonical revision witness.")
        responses.append({})
        vfx._request(stage.call_llm_vfx_director, vfx._prompt_packet(data, None, None), **kwargs)
        packets.append(json.loads(sent[-1]["messages"][1]["content"]))
    before, after = packets
    assert before[vocabulary_key]["rendererSemantics"]["impactSprite"] == original_semantics
    assert after[vocabulary_key]["rendererSemantics"]["impactSprite"] == vfx._RENDERER_SEMANTICS["impactSprite"]
    assert _static_json_prefix(before, keys) != _static_json_prefix(after, keys)
    assert {k: v for k, v in before.items() if k != vocabulary_key} == {k: v for k, v in after.items() if k != vocabulary_key}
    # A future unclassified canonical field must be retained, but not made static.
    canonical = vfx.vfx_director_surface
    monkeypatch.setattr(vfx, "vfx_director_surface", lambda source: {**canonical(source), "futureAcceptedFact": source["runtimeProgram"]["primaryEntityId"]})
    responses.append({})
    vfx._request(stage.call_llm_vfx_director, vfx._prompt_packet(data, None, None), **kwargs)
    extended = json.loads(sent[-1]["messages"][1]["content"])
    assert _static_json_prefix(extended, keys) == _static_json_prefix(after, keys)
    assert extended[surface_key] == {**after[surface_key], "futureAcceptedFact": data["runtimeProgram"]["primaryEntityId"]}
    assert data == frozen


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
        {"mode": "baked_sprite", "runtimeEffect": "Generate and deliver a distinct PNG for this exact runtime entity. item_body owns the root item project; a distinct entity owns its renderSizePx, preferredCanvasSize and forwardAngleDegrees."},
        {"mode": "no_asset", "runtimeEffect": "Deliver no PNG and draw no entity body; independent runtime VFX may still draw."},
        {"mode": "reuse_item_icon", "runtimeEffect": "Deliver no separate PNG; resolve this entity to the item_body generated PNG with identical pixels, root base renderSizePx, canvas and forwardAngleDegrees. No own prompt/size/canvas/axis; entity scale remains independent."},
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
        assert payload["parentFactsReadOnly"]["parentA"] == {"packet": visual.raw_parent_card_for_llm(parent, include_visual_reference=True)}
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
    branches = (props["entities"] if kind == "director" else props["entitiesUpsert"])["items"]["anyOf"]
    assert {b["properties"]["assetMode"]["const"] for b in branches} == {"baked_sprite", "reuse_item_icon", "runtime_geometry", "no_asset"}
    descriptions = {b["properties"]["scale"]["description"] for b in branches}
    assert len(descriptions) == 1
    assert all(b["properties"]["scale"]["minimum"] == 0.25 and b["properties"]["scale"]["maximum"] == 4.0 for b in branches)
    assert all(token in next(iter(descriptions)).lower() for token in ("visual", "factor", "1", "hitbox", "drawscale", "worldscale"))

@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("fixture", ["workbench_blade", "door_on_chain", "returning_potion"])
def test_actual_visual_packets_carry_exact_mechanics_sizing_axis_and_fill(wire_transport, monkeypatch, format_mode, repair, fixture):
    from infini_local.pipelines import llm_transport
    from infini_local.pipelines.sprite_contracts import sprite_contract_for
    responses, sent = wire_transport
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    data = _craft(fixture)
    before = copy.deepcopy(data)
    responses.append({})
    kwargs = {"repair_errors": [{"path": "$.item.renderSizePx", "message": "required"}], "previous": {"item": {}}, "repair_scope": {}} if repair else {}
    visual._request_visual_kit(data, {}, {}, {}, {}, **kwargs)
    request = sent[-1]
    packet = json.loads(request["messages"][1]["content"])
    context = packet["acceptedPresentationMechanicsReadOnly"]
    runtime = data["runtimeProgram"]
    assert context["gameplay"] == {k: data["gameplay"][k] for k in ("itemScale", "width", "height") if k in data["gameplay"]}
    for field in ("itemEntityId", "primaryEntityId", "primaryOwner", "itemUse", "itemContact", "bindings"):
        assert (field in context) == (field in runtime)
        if field in runtime:
            assert context[field] == runtime[field]
    rows = packet["runtimeEntitiesReadOnly" if repair else "runtimeEntities"]
    for row, accepted in zip(rows, runtime["entities"]):
        assert row["hitbox"] == accepted.get("hitbox", {})
        assert row["movement"] == accepted.get("movement", {})
        assert row["controller"] == accepted.get("controller", {})
    presentation = packet["spritePresentationReadOnly"]
    assert presentation["formulas"]["q"] == "R / max(actual final PNG frame width, height)"
    assert presentation["formulas"]["held"] == "q_item * player.GetAdjustedItemScale(held) (G already included once)"
    assert presentation["formulas"]["body"] == "q_selected * clamp(P, .1, 8); initial P=D*E, growth remains independent"
    assert "alpha-bbox" in presentation["units"] and "positive clockwise" in presentation["axis"]
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    use = CAPABILITY_REGISTRY["configure_item_use"].params
    assert presentation["heldRootVisibility"]["hideUseGraphic"] == use["hideUseGraphic"].description
    assert presentation["heldRootVisibility"]["heldSpriteVisibilityHint"] == use["heldSpriteVisibilityHint"].description
    assert presentation["heldRootVisibility"]["wireHint"] == "runtimeProgram.itemUse.releaseTiming"

    for role, by_canvas in presentation["bakeFillByProcessingRole"].items():
        for canvas, facts in by_canvas.items():
            canonical = sprite_contract_for(role, int(canvas))
            assert facts == {field: canonical[field] for field in ("targetFill", "minFill", "maxFill", "marginPx", "cropPadPx", "targetLongAxisPx", "alphaMode")}
    schema = packet["responseSchema"]
    item = schema["properties"]["itemPatch"]["anyOf"][0] if repair else schema["properties"]["item"]
    if not repair:
        assert {"renderSizePx", "forwardAngleDegrees"}.issubset(item["required"])
    elif format_mode == "json_object":
        assert "required" not in item
    branch_key = "anyOf" if format_mode == "json_schema" else "oneOf"
    branches = schema["properties"]["entitiesUpsert" if repair else "entities"]["items"][branch_key]
    item_branch = next(b for b in branches if b["properties"]["assetMode"]["const"] == "baked_sprite" and b["properties"]["visualProjectRef"]["const"] == "item")
    assert item_branch["properties"]["entityId"]["enum"] == [runtime["itemEntityId"]]
    distinct = next(b for b in branches if b["properties"]["assetMode"]["const"] == "baked_sprite" and b["properties"]["visualProjectRef"]["const"] == "entity")
    assert {"renderSizePx", "preferredCanvasSize", "forwardAngleDegrees"}.issubset(distinct["required"])
    assert runtime["itemEntityId"] not in distinct["properties"]["entityId"]["enum"]
    assert data == before


@pytest.mark.parametrize("repair", [False, True])
def test_exact_single_item_schema_contains_only_its_project_and_no_empty_enums(repair):
    schema = (visual.visual_repair_schema if repair else visual.visual_response_schema)(["opaque_root"], False, item_body_id="opaque_root")
    branch_schema = schema["properties"]["entitiesUpsert" if repair else "entities"]["items"]
    branches = branch_schema.get("oneOf", [branch_schema])
    assert len(branches) == 1
    assert branches[0]["properties"]["assetMode"]["const"] == "baked_sprite"
    assert branches[0]["properties"]["visualProjectRef"]["const"] == "item"
    assert branches[0]["properties"]["entityId"]["enum"] == ["opaque_root"]


@pytest.mark.parametrize("repair", [False, True])
def test_exact_schema_nonitem_branches_exclude_item_authority(repair):
    schema = (visual.visual_repair_schema if repair else visual.visual_response_schema)(["opaque_root", "opaque_body"], False, item_body_id="opaque_root")
    branches = schema["properties"]["entitiesUpsert" if repair else "entities"]["items"]["oneOf"]
    for branch in branches:
        props = branch["properties"]
        if props["assetMode"]["const"] == "baked_sprite" and props["visualProjectRef"]["const"] == "item":
            continue
        assert props["entityId"]["enum"] == ["opaque_body"]


# Append to existing test_visual_vfx_prompt_prefix.py; uses its _craft and wire_transport.
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm


@pytest.mark.parametrize("kind", ["director", "scoped-repair", "malformed-repair"])
@pytest.mark.parametrize("reference", ["native-static", "native-animated", "older-missing", "generated-declared-and-old"])
def test_parent_sprite_reference_reaches_actual_visual_request_only(wire_transport, kind, reference):
    responses, sent = wire_transport
    data = _craft("workbench_blade")
    parent_a, parent_b = {"id": 1, "name": "unrelated name A", "damage": 17}, {"id": 1, "name": "unrelated name B", "damage": 19}
    if reference.startswith("native"):
        for parent, width in ((parent_a, 40), (parent_b, 73)):
            animated = reference == "native-animated"
            parent["spriteReferenceRaw"] = {"source": "TextureAssets.Item", "textureWidthPx": width, "textureHeightPx": 68,
                "currentFrame": {"source": "draw_animation" if animated else "texture_bounds", "xPx": 0,
                    "yPx": 34 if animated else 0, "widthPx": width, "heightPx": 32 if animated else 68}}
    elif reference == "generated-declared-and-old":
        for parent, identifier in ((parent_a, "definition-a"), (parent_b, "definition-b")):
            parent["generatedData"] = {"id": identifier, "visual": {"preferredCanvasSize": 32, "worldScale": 4},
                "gameplay": {"width": 64, "height": 32}, "runtimeProgram": {"entities": [], "bindings": []}}
            parent["spriteReferenceRaw"] = {"source": "TextureAssets.Item", "textureWidthPx": 1, "textureHeightPx": 1}
        parent_a["generatedData"]["visual"]["renderSizePx"] = 47
    frozen = copy.deepcopy((parent_a, parent_b))
    malformed = kind == "malformed-repair"
    scope = {"itemMutable": True, "fieldPermissions": {"itemPaths": ["" if malformed else "silhouette"]}}
    kwargs = {} if kind == "director" else {
        "repair_errors": [{"path": "$" if malformed else "$.item.silhouette", "message": "malformed_json" if malformed else "required"}],
        "previous": visual.MalformedVisualDirectorOutput("{broken", "bad json") if malformed else {"schema": visual.VISUAL_KIT_SCHEMA, "item": {"prompt": "literal"}, "entities": []},
        "repair_scope": scope,
    }
    responses.append({})
    assert visual._request_visual_kit(data, parent_a, parent_b, {}, {}, **kwargs) == {}
    payload = json.loads(sent[-1]["messages"][1]["content"])
    packet_root = payload["parents"] if kind == "director" else payload["parentFactsReadOnly"]
    for name, parent in (("parentA", parent_a), ("parentB", parent_b)):
        actual = packet_root[name]["packet"]
        assert actual == raw_parent_card_for_llm(parent, include_visual_reference=True)
        gameplay = raw_parent_card_for_llm(parent)
        assert "spriteReference" not in gameplay["raw"]
        if "generatedParent" in gameplay["raw"]:
            assert "visual" not in gameplay["raw"]["generatedParent"]
        if reference.startswith("native"):
            assert actual["raw"]["spriteReference"] == parent["spriteReferenceRaw"]
        elif reference == "generated-declared-and-old":
            assert "spriteReference" not in actual["raw"]
            if name == "parentA":
                assert actual["raw"]["generatedParent"]["visual"] == {"renderSizePx": 47}
            else:
                assert "visual" not in actual["raw"]["generatedParent"]
        else:
            assert "spriteReference" not in actual["raw"]
    assert (parent_a, parent_b) == frozen
    assert "spriteReference" not in json.dumps(payload["responseSchema"])
    if kind != "director":
        assert payload["repairScope"] == scope
        assert "spriteReference" not in json.dumps(payload["repairScope"])
    # Parent calibration remains in the dynamic tail, never a cache-static prefix.
    prefix = _static_json_prefix(payload, ("task", "assetModeCatalog", "rules"))
    assert '"textureWidthPx"' not in prefix and '"textureHeightPx"' not in prefix
    assert '"spriteReferenceRaw"' not in prefix
    assert sent[-1]["_infini_prompt_cache"] == {"messageIndex": 1, "prefixChars": len(prefix)}
    if reference != "older-missing":
        changed = copy.deepcopy(parent_a)
        if reference.startswith("native"):
            changed["spriteReferenceRaw"]["textureWidthPx"] += 1
            changed["spriteReferenceRaw"]["currentFrame"]["widthPx"] += 1
        else:
            changed["generatedData"]["visual"]["renderSizePx"] = 48
        responses.append({})
        visual._request_visual_kit(data, changed, parent_b, {}, {}, **kwargs)
        after = json.loads(sent[-1]["messages"][1]["content"])
        assert _static_json_prefix(after, ("task", "assetModeCatalog", "rules")) == prefix
        after_root = after["parents"] if kind == "director" else after["parentFactsReadOnly"]
        assert after_root["parentA"]["packet"] == raw_parent_card_for_llm(changed, include_visual_reference=True)
        assert after_root["parentA"]["packet"] != packet_root["parentA"]["packet"]
        assert after_root["parentB"]["packet"] == packet_root["parentB"]["packet"]
        assert (parent_a, parent_b) == frozen


def test_parent_visual_reference_does_not_enter_actual_gameplay_author_packet(wire_transport):
    import infini_local.pipelines.llm_authoring_pipeline as gameplay_stage
    responses, sent = wire_transport
    native = {"id": 1, "name": "literal native", "damage": 17,
              "spriteReferenceRaw": {"source": "TextureAssets.Item", "textureWidthPx": 40, "textureHeightPx": 16}}
    generated = {"id": 1, "name": "literal generated", "generatedData": {"id": "canonical-parent",
                 "gameplay": {"damage": 19}, "visual": {"renderSizePx": 47},
                 "runtimeProgram": {"entities": [], "bindings": []}}}
    responses.append(build_runtime_fixture("workbench_blade"))
    assert gameplay_stage.try_llm_plan(native, generated, {}, {}, "parent-reference-gameplay-control") is not None
    payload = json.loads(sent[-1]["messages"][1]["content"])
    assert payload["parents"]["A"]["packet"] == raw_parent_card_for_llm(native)
    assert payload["parents"]["B"]["packet"] == raw_parent_card_for_llm(generated)
    encoded = json.dumps(payload["parents"])
    assert "spriteReference" not in encoded and "renderSizePx" not in encoded

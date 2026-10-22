"""Real current-stage sender packets: authority, provider grammar and consumers.

No source-string locks, invented provider replies, live calls or native launch.
Useful nonexecuted artist prose is not a retired executable contract field.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.diagnostics.measure_llm_request_sizes import (  # noqa: E402
    COHORT, MODES, ROUTES, STAGES, OfflineCapture, dossier, measurements,
)

RETIRED_SLOT_FIELDS = {
    "backend", "particleRole", "jitter", "fadeIn", "fadeOut", "budgetWeight",
    "signatureWeight", "visualCost", "channel", "lane", "emissionMode",
}
RETIRED_GLOBAL_FIELDS = {"motif", "effectMagnitude", "visualBudgetClass"}


@pytest.fixture
def capture():
    with OfflineCapture(ROOT) as actual:
        yield actual


def text(row):
    value = row["content"]
    return value if isinstance(value, str) else "".join(block["text"] for block in value)


def schema_from_wire(wire):
    wrapper = wire.get("response_format", wire.get("text", {}).get("format"))
    return wrapper.get("json_schema", wrapper).get("schema") if isinstance(wrapper, dict) else None


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("mode", MODES)
def test_actual_outgoing_packets_preserve_roles_schema_and_frozen_authority(capture, stage, mode):
    packet, evidence = capture.builder(stage, COHORT[0], mode)
    full = dossier(packet)
    before = copy.deepcopy(packet)
    retired_keys = (RETIRED_SLOT_FIELDS - {"channel", "backend"}) | RETIRED_GLOBAL_FIELDS | {
        "effectColor", "parent_power_context", "itemKnowledge", "powerKnowledge", "rarityBaseline",
        "behaviorDigest", "exampleAmmo", "exampleProjectile", "selectedPlayerAmmoRaw",
        "representativeAmmoRaw", "playerInventoryAmmoRaw", "fallbackAmmoRaw",
        "animationPlanMutable", "LLM_RAW_TOKEN_MODE", "maxConceptCandidates",
    }
    # Inspect every actual sender surface, including JSON embedded in messages,
    # dynamic parent facts, provider schema, tools and frozen Repair context.
    # Compare structural keys, not artist-written prose containing ordinary words.
    def assert_current_keys(value):
        for node in dict_nodes(value):
            assert not node.keys() & retired_keys
            for child in node.values():
                if isinstance(child, str) and child.lstrip().startswith(("{", "[")):
                    try:
                        decoded = json.loads(child)
                    except ValueError:
                        continue
                    assert_current_keys(decoded)
    assert_current_keys(packet)
    assert [row["role"] for row in packet["messages"]] == ["system", "developer", "user"]
    static = json.loads(packet["messages"][1]["content"])
    dynamic = json.loads(packet["messages"][2]["content"])
    assert not static.keys() & dynamic.keys()
    assert not static.keys() & {"parents", "parentFactsReadOnly", "repairScope", "brokenFragments", "originalRecipeContext"}
    if stage in {"visual_repair", "vfx_repair"}:
        assert full["repairScope"] == evidence["repairScope"]
        permissions = full["repairScope"]["fieldPermissions"]
        if stage == "visual_repair":
            assert permissions["itemPaths"] == ["renderSizePx"]
            assert permissions["entities"] == []
        else:
            assert permissions["slots"] == [{"slotId": evidence["broken"]["slots"][0]["id"], "paths": ["alpha"]}]
            assert not full["repairScope"]["allowCreateSlots"]
    elif stage == "gameplay_repair":
        expected = capture.author.build_gameplay_repair_dossier(evidence["broken"],
            evidence["inputs"]["parentA"], evidence["inputs"]["parentB"], failure_report=evidence["failureReport"])
        assert full["repairScope"] == expected["repairScope"]
        assert full["acceptedItemContext"]["runtimeProgram"] == evidence["broken"]["runtimeProgram"]
        assert full["repairScope"]["fieldPermissions"]
    elif stage == "format_repair":
        assert full["malformedRawText"] == evidence["malformedRawText"]
        assert "originalRecipeContext" not in full, "syntax-only repair has one exact design source"

    for route in ROUTES:
        observed = capture.wire(packet, route)
        wire = observed["packet"]
        assert_current_keys(wire)
        assert observed["method"] == "POST"
        # Exact bytes are serialized by production, not a test's compact encoder.
        assert json.loads(observed["body"]) == wire
        assert not any(key.startswith("_infini") for key in wire)
        assert wire.get("tools", []) == []
        if route == "chat_completions":
            source = packet["messages"]
        else:
            assert wire["instructions"] == packet["messages"][0]["content"]
            source = packet["messages"][1:]
        rows = wire.get("messages", wire.get("input"))
        rows = [row for row in rows if text(row) != "JSON response."]
        assert [(row["role"], text(row)) for row in rows] == [(row["role"], row["content"]) for row in source]
        schema = schema_from_wire(wire)
        if mode == "json_schema":
            assert schema == packet["response_format"]["json_schema"]["schema"]
            if stage.startswith(("visual", "vfx")):
                assert schema == full["responseSchema" if stage.startswith("visual") else "outputSchema"]
                assert not any("$ref" in node for node in dict_nodes(schema))
        else:
            assert schema is None
        measured = measurements(packet, observed)
        assert measured["httpBody"] == {"unicodeChars": len(observed["body"]), "utf8Bytes": len(observed["body"].encode("utf-8"))}
        if stage in {"gameplay_repair", "visual_repair", "vfx_repair"}:
            assert measured["repairPermissionsCompact"]
    assert packet == before


def test_author_and_format_provider_shape_matches_actual_author_consumer(capture):
    from infini_local.pipelines.author_item_contract import author_item_response_schema
    from test_codex_subscription_contract import _encode_nullable_fixture
    for stage in ("author", "format_repair"):
        packet, evidence = capture.builder(stage, COHORT[0], "json_schema")
        schema = schema_from_wire(capture.wire(packet, "responses")["packet"])
        source = copy.deepcopy(evidence["inputs"]["authored"])
        # QA fixtures retain historical rich advisory reports. The current
        # provider grammar advertises optional prose; no report is required.
        source.pop("realization", None)
        valid = _encode_nullable_fixture(source, author_item_response_schema())
        invalid = copy.deepcopy(valid)
        invalid["runtimeProgram"]["calls"][0]["fn"] = "unknown_operation"
        for wire_value, expected in ((valid, True), (invalid, False)):
            assert Draft202012Validator(schema).is_valid(wire_value) is expected
            local = capture.author._prepare_parsed_author_item(wire_value, response_format=packet["response_format"])
            assert capture.validate(local)["ok"] is expected


@pytest.mark.parametrize("stage", ["visual_repair", "vfx_repair", "gameplay_repair"])
def test_captured_permissions_drive_real_frozen_merge_not_provider_schema_alone(capture, stage):
    from infini_local.pipelines.author_item_contract import author_item_repair_response_schema
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair_scope import filter_repair_patch_scope
    from test_codex_subscription_contract import _encode_nullable_fixture
    packet, evidence = capture.builder(stage, COHORT[0], "json_schema")
    full = dossier(packet)
    scope = full["repairScope"]
    inputs, broken = evidence["inputs"], evidence["broken"]
    provider_schema = schema_from_wire(capture.wire(packet, "responses")["packet"])
    assert isinstance(provider_schema, dict)
    if stage == "visual_repair":
        patch = {"schema": capture.visual.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": {"renderSizePx": 40, "inventoryScale": 2.0},
                 "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [], "note": "one leaf"}
        ids = [row["id"] for row in inputs["data"]["runtimeProgram"]["entities"]]
        valid = {"schema": patch["schema"], "itemPatch": {"renderSizePx": 40}, "note": "one leaf"}
        assert Draft202012Validator(provider_schema).is_valid(valid)
        assert not Draft202012Validator(provider_schema).is_valid(patch)
        fixed, audit = capture.visual._apply_visual_repair_patch(broken, patch, scope, ids, return_audit=True)
        assert fixed == inputs["visualKit"]
        assert audit["ignoredChanges"]
    elif stage == "vfx_repair":
        slot = copy.deepcopy(inputs["vfxOutput"]["slots"][0])
        slot["duration"] = 100
        patch = {"schema": capture.vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [slot], "note": "one leaf"}
        valid = {"schema": patch["schema"], "slotsUpsert": inputs["vfxOutput"]["slots"], "note": "one leaf"}
        assert Draft202012Validator(provider_schema).is_valid(valid)
        assert not Draft202012Validator(provider_schema).is_valid(patch)
        fixed, audit = capture.vfx._apply_vfx_repair_patch(inputs["visualData"], broken, patch, scope, return_audit=True)
        assert fixed == inputs["vfxOutput"]
        assert audit["ignoredChanges"]
    else:
        correct = next(row for row in inputs["authored"]["runtimeProgram"]["calls"] if row["fn"] == "configure_item_use")
        candidate = copy.deepcopy(correct)
        candidate["params"]["autoReuse"] = not correct["params"]["autoReuse"]
        patch = {"callsUpsert": [candidate], "note": "one leaf"}
        assert Draft202012Validator(provider_schema).is_valid(_encode_nullable_fixture(patch, author_item_repair_response_schema()))
        filtered, audit = filter_repair_patch_scope(broken, patch, scope)
        fixed = apply_repair_patch(broken, filtered)
        assert fixed["runtimeProgram"] == inputs["authored"]["runtimeProgram"]
        assert audit["ignoredChanges"]


def dict_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from dict_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from dict_nodes(child)


@pytest.mark.parametrize("stage", [stage for stage in STAGES if stage not in {"vfx_repair", "format_repair"}])
def test_changed_parent_context_is_dynamic_and_retains_generated_facts(capture, stage):
    first, _ = capture.builder(stage, COHORT[0], "json_object")
    # Compare the same runtime/overlay grammar with changed parent facts; an
    # equipment fixture legitimately has additional invariant overlay grammar.
    a, b, _ = capture.recipes[COHORT[2]]
    capture.recipes[COHORT[2]] = (a, b, capture.recipes[COHORT[0]][2])
    second, _ = capture.builder(stage, COHORT[2], "json_object")
    assert first["messages"][:2] == second["messages"][:2]
    assert first["messages"][2] != second["messages"][2]
    full = dossier(second)

    parents = full.get("parents", full.get("parentFactsReadOnly", full.get("parentSizeReferencesReadOnly")))
    assert parents
    if stage != "visual_repair":
        assert "held_and_deployed" in json.dumps(parents)
        assert "equipment_tool_combat" in json.dumps(parents)
    else:
        assert parents != dossier(first)["parentSizeReferencesReadOnly"]
        for key, parent in (("parentA", a), ("parentB", b)):
            source = capture.visual.raw_parent_card_for_llm(parent, include_visual_reference=True)["raw"]["generatedParent"]
            assert parents[key]["entities"] == [
                {"id": row["id"], **({"visual": row["visual"]} if "visual" in row else {})}
                for row in source["runtimeProgram"]["entities"]
            ]


@pytest.mark.parametrize("stage", ["visual", "visual_repair", "vfx", "vfx_repair"])
def test_current_grammar_removes_only_obsolete_controls_not_artist_prose(capture, stage):
    packet, evidence = capture.builder(stage, COHORT[0], "json_schema")
    full = dossier(packet)
    schema = full["responseSchema" if stage.startswith("visual") else "outputSchema"]
    if stage.startswith("visual"):
        for node in dict_nodes(schema):
            assert "effectColor" not in node.get("properties", {})
            assert "effectColor" not in node.get("required", [])
        # Prompt/silhouette/identity and descriptive palette remain design tools.
        if stage == "visual":
            assert any("palette" in node.get("properties", {}) for node in dict_nodes(schema))
        else:
            assert set(schema["properties"]["itemPatch"]["anyOf"][0]["properties"]) == {"renderSizePx"}
            assert full["brokenFragments"]["item"]["prompt"] == evidence["broken"]["item"]["prompt"]
    else:
        props = schema["properties"]
        assert not props.keys() & RETIRED_GLOBAL_FIELDS
        slot = props["slotsUpsert" if stage.endswith("repair") else "slots"]["items"]
        assert not slot["properties"].keys() & RETIRED_SLOT_FIELDS
        rgb = slot["properties"]["color"]
        if stage == "vfx":
            assert set(rgb["properties"]) == {"r", "g", "b"}
            for channel in rgb["properties"].values():
                assert channel["type"] == "integer" and channel["minimum"] == 0 and channel["maximum"] == 255
        else:
            assert rgb["const"] == evidence["broken"]["slots"][0]["color"]
            assert rgb["type"] == "object" and rgb["additionalProperties"] is False
            assert set(rgb["required"]) == {"r", "g", "b"}
            for channel, value in rgb["const"].items():
                assert rgb["properties"][channel] == {"const": value, "type": "integer"}
            assert slot["properties"]["alpha"]["maximum"] == 1.0
        # Frozen context must not carry the retired global model as current data.
        for key in ("brokenFragments", "validGeneratedContext", "item", "itemReadOnly"):
            assert not (full.get(key) or {}).keys() & RETIRED_GLOBAL_FIELDS
    assert evidence["inputs"]["visualKit"]["item"]["prompt"]


@pytest.mark.parametrize("domain", ["visual", "vfx"])
def test_provider_schema_and_real_consumer_accept_same_control_refusals(capture, domain):
    from test_codex_subscription_contract import _encode_nullable_fixture
    packet, evidence = capture.builder(domain, COHORT[0], "json_schema")
    inputs = evidence["inputs"]
    schema = schema_from_wire(capture.wire(packet, "responses")["packet"])
    valid = copy.deepcopy(inputs["visualKit" if domain == "visual" else "vfxOutput"])
    if domain == "visual":
        ids = [row["id"] for row in inputs["data"]["runtimeProgram"]["entities"]]
        item_id = inputs["data"]["runtimeProgram"]["itemEntityId"]
        local = capture.visual._response_schema(ids, False, item_id)
        def encode(value):
            # Nullable fixture projection intentionally drops unknown keys; the
            # provider refusal control must retain an actually outgoing unknown.
            projected = _encode_nullable_fixture(value, local)
            if "effectColor" in value["item"]:
                projected["item"]["effectColor"] = value["item"]["effectColor"]
            return projected
        accepted = lambda value: capture.visual._validate_kit(value, ids, item_id)[0] is not None
        invalid = copy.deepcopy(valid)
        invalid["item"]["inventoryScale"] = True
        retired = copy.deepcopy(valid)
        retired["item"]["effectColor"] = "gold"
    else:
        encode = lambda value: value
        accepted = lambda value: capture.vfx.validate_vfx_director_output(value, inputs["visualData"])["ok"]
        invalid = copy.deepcopy(valid)
        invalid["slots"][0]["color"]["r"] = True
        retired = copy.deepcopy(valid)
        retired["effectMagnitude"] = 0.5
    for value, expected in ((valid, True), (invalid, False), (retired, False)):
        assert Draft202012Validator(schema).is_valid(encode(value)) is expected
        assert accepted(value) is expected
